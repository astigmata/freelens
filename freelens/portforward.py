"""Server-side TCP port-forwards into pods and services.

This is ``kubectl port-forward`` run inside the app: a local TCP listener on the
server is bridged, connection by connection, to a pod's port through the
Kubernetes port-forward API (a WebSocket stream). Forwarding to a Service first
resolves a ready backing pod and the pod-side target port, since the
port-forward subresource only exists on pods (see ``operations.resolve_forward_target``).

Security: a forwarded port is a raw TCP bridge into the pod with no
authentication of its own. Listeners therefore bind to loopback by default
(``FREELENS_FORWARD_BIND_HOST``); a non-loopback bind is refused unless
``FREELENS_ALLOW_INSECURE`` is set, mirroring the startup bind guard. Every
start and stop is audited by the caller.
"""

import logging
import select
import socketserver
import threading
from dataclasses import dataclass
from itertools import count

from kubernetes.client import CoreV1Api
from kubernetes.stream import portforward

from . import config

log = logging.getLogger(__name__)

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
# Bytes shovelled per read; small enough to stay responsive, large enough to be
# efficient for the bulk-transfer case.
_CHUNK = 65536


@dataclass(frozen=True)
class Forward:
    """A live port-forward: a local listener bridged to ``pod:remote_port``."""

    id: int
    kind: str  # the resource the user selected ("pods" | "services")
    name: str  # its name
    namespace: str
    pod: str  # the pod actually forwarded to (== name for pods)
    remote_port: int  # the pod-side port
    local_port: int  # the bound local port
    address: str  # host:port the listener is reachable at


def _make_handler(core: CoreV1Api, pod: str, namespace: str, remote_port: int):
    """A request handler class that bridges each accepted TCP connection."""

    class _Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                forward = portforward(
                    core.connect_get_namespaced_pod_portforward,
                    pod,
                    namespace,
                    ports=str(remote_port),
                )
                kube_sock = forward.socket(remote_port)
            except Exception:
                log.exception(
                    "port-forward: failed to open stream to %s/%s:%s",
                    namespace, pod, remote_port,
                )
                return
            _pump(self.request, kube_sock)

    return _Handler


def _pump(client_sock, kube_sock) -> None:
    """Shovel bytes both ways until either side closes."""
    client_sock.setblocking(False)
    kube_sock.setblocking(False)
    socks = [client_sock, kube_sock]
    try:
        while True:
            readable, _, errored = select.select(socks, [], socks, 1.0)
            if errored:
                break
            for sock in readable:
                other = kube_sock if sock is client_sock else client_sock
                try:
                    data = sock.recv(_CHUNK)
                except BlockingIOError:
                    continue
                except OSError:
                    return
                if not data:
                    return
                try:
                    other.sendall(data)
                except OSError:
                    return
    finally:
        for sock in socks:
            try:
                sock.close()
            except OSError:
                pass


class _Manager:
    """Process-wide registry of active port-forwards."""

    def __init__(self) -> None:
        self._forwards: dict[int, tuple[Forward, socketserver.TCPServer]] = {}
        self._ids = count(1)
        self._lock = threading.Lock()

    def list(self) -> list[Forward]:
        with self._lock:
            return [fwd for fwd, _ in self._forwards.values()]

    def start(
        self,
        core: CoreV1Api,
        kind: str,
        name: str,
        namespace: str,
        pod: str,
        remote_port: int,
        local_port: int = 0,
    ) -> Forward:
        """Open a local listener bridged to ``pod:remote_port`` and track it.

        ``local_port`` 0 picks an ephemeral free port. ``core`` is captured here
        so the bridge keeps working (with the user's impersonation headers)
        outside any request context.
        """
        host = config.FORWARD_BIND_HOST
        if host not in _LOOPBACK_HOSTS and not config.ALLOW_INSECURE:
            raise ValueError(
                f"Refusing to bind a port-forward to non-loopback '{host}': the "
                "bridged port is unauthenticated. Set FREELENS_ALLOW_INSECURE=true "
                "to override on an already-isolated network."
            )

        handler = _make_handler(core, pod, namespace, int(remote_port))

        class _Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        server = _Server((host, int(local_port or 0)), handler)
        bound_host, bound_port = server.server_address[:2]
        fid = next(self._ids)
        fwd = Forward(
            id=fid,
            kind=kind,
            name=name,
            namespace=namespace,
            pod=pod,
            remote_port=int(remote_port),
            local_port=bound_port,
            address=f"{bound_host}:{bound_port}",
        )
        threading.Thread(
            target=server.serve_forever, name=f"port-forward-{fid}", daemon=True
        ).start()
        with self._lock:
            self._forwards[fid] = (fwd, server)
        log.info("port-forward %s started: %s -> %s/%s:%s",
                 fid, fwd.address, namespace, pod, remote_port)
        return fwd

    def stop(self, fid: int) -> Forward | None:
        with self._lock:
            entry = self._forwards.pop(fid, None)
        if entry is None:
            return None
        fwd, server = entry
        server.shutdown()
        server.server_close()
        log.info("port-forward %s stopped: %s", fid, fwd.address)
        return fwd


# Single process-wide manager. Port-forwards are server-side state, not tied to
# a request, so they live here rather than in a Dash store.
MANAGER = _Manager()
