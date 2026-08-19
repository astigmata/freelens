"""Operations on Kubernetes objects: YAML rendering, logs and write actions.

Kept separate from the read-only listing logic in ``registry`` so that the
mutating calls (scale / restart / delete) live in one auditable place.
"""

import datetime

import yaml
from kubernetes import client as k8s

from .client import Clients

# Secret kinds whose value maps must never be rendered. The base64 in a Secret's
# ``data`` is only an encoding, not encryption, so dumping it leaks the value.
_SECRET_VALUE_KEYS = ("data", "stringData")


def _redact_secret(data: dict) -> dict:
    """Replace Secret value maps with a placeholder, keeping the key names.

    The detail panel already shows only key names on purpose; this keeps the YAML
    tab consistent and avoids leaking credentials (and possibly PHI) in clear.
    """
    if not isinstance(data, dict) or data.get("kind") != "Secret":
        return data
    for key in _SECRET_VALUE_KEYS:
        values = data.get(key)
        if isinstance(values, dict):
            data[key] = {name: "<redacted>" for name in values}
    return data


def to_yaml(obj) -> str:
    """Serialize a Kubernetes API object to a clean YAML manifest.

    Secret values are redacted: their base64 ``data`` is an encoding, not a
    protection, so it is never rendered.
    """
    data = k8s.ApiClient().sanitize_for_serialization(obj)
    # The typed read API does not always populate kind/apiVersion; set it from
    # the Python type so the redaction below can recognise a Secret.
    if isinstance(obj, k8s.V1Secret):
        data["kind"] = "Secret"
    data = _redact_secret(data)
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


def list_containers(clients: Clients, name: str, namespace: str) -> list[str]:
    pod = clients.core.read_namespaced_pod(name, namespace)
    return [c.name for c in pod.spec.containers]


def list_ports(clients: Clients, kind: str, name: str, namespace: str) -> list[dict]:
    """TCP ports exposed by a pod or service, as ``{"label", "value"}`` options.

    Pods often declare no container ports; an empty list is returned then and the
    UI falls back to a free-form port input.
    """
    options: list[dict] = []
    if kind == "services":
        svc = clients.core.read_namespaced_service(name, namespace)
        for p in svc.spec.ports or []:
            if (p.protocol or "TCP") != "TCP":
                continue
            label = f"{p.port}" + (f" ({p.name})" if p.name else "")
            options.append({"label": label, "value": p.port})
        return options

    pod = clients.core.read_namespaced_pod(name, namespace)
    for container in pod.spec.containers:
        for cp in container.ports or []:
            if (cp.protocol or "TCP") != "TCP":
                continue
            name_part = f" ({cp.name})" if cp.name else ""
            options.append(
                {"label": f"{cp.container_port}{name_part} — {container.name}",
                 "value": cp.container_port}
            )
    return options


def _pick_ready_pod(pods: list):
    """Choose a Running+Ready pod, falling back to any Running pod.

    Never returns a non-Running pod: port-forwarding to a Pending/Terminating
    pod would only fail opaquely once a connection is attempted.
    """
    running = [p for p in pods if p.status and p.status.phase == "Running"]
    for pod in running:
        if any(
            c.type == "Ready" and c.status == "True"
            for c in (pod.status.conditions or [])
        ):
            return pod
    return running[0] if running else None


def _named_container_port(pod, port_name: str) -> int | None:
    for container in pod.spec.containers:
        for cp in container.ports or []:
            if cp.name == port_name:
                return cp.container_port
    return None


def resolve_forward_target(
    clients: Clients, kind: str, name: str, namespace: str, remote_port: int
) -> tuple[str, int]:
    """Resolve the (pod, pod_port) to port-forward to.

    The port-forward subresource exists only on pods, so forwarding to a Service
    means picking a ready backing pod (via its selector) and translating the
    service port to that pod's target port (resolving a named target port too).
    """
    if kind != "services":
        return name, int(remote_port)

    svc = clients.core.read_namespaced_service(name, namespace)
    service_port = next(
        (p for p in (svc.spec.ports or []) if p.port == int(remote_port)), None
    )
    if service_port is None:
        raise ValueError(f"Service '{name}' has no port {remote_port}")
    selector = svc.spec.selector or {}
    if not selector:
        raise ValueError(f"Service '{name}' has no selector to find backing pods")

    label_selector = ",".join(f"{k}={v}" for k, v in selector.items())
    pods = clients.core.list_namespaced_pod(
        namespace, label_selector=label_selector
    ).items
    pod = _pick_ready_pod(pods)
    if pod is None:
        raise ValueError(f"Service '{name}' has no ready backing pod")

    target = service_port.target_port
    if target is None:
        target = service_port.port
    if isinstance(target, str):
        resolved = _named_container_port(pod, target)
        if resolved is None:
            raise ValueError(
                f"Could not resolve named port '{target}' on pod '{pod.metadata.name}'"
            )
        target = resolved
    return pod.metadata.name, int(target)


def pod_logs(
    clients: Clients,
    name: str,
    namespace: str,
    container: str | None = None,
    tail_lines: int = 500,
) -> str:
    return clients.core.read_namespaced_pod_log(
        name,
        namespace,
        container=container,
        tail_lines=tail_lines,
        timestamps=True,
    )


# --------------------------------------------------------------------------- #
# Write actions.
# --------------------------------------------------------------------------- #
def scale_deployment(clients: Clients, name: str, namespace: str, replicas: int) -> None:
    clients.apps.patch_namespaced_deployment_scale(
        name, namespace, {"spec": {"replicas": int(replicas)}}
    )


def restart_deployment(clients: Clients, name: str, namespace: str) -> None:
    """Trigger a rolling restart, the way ``kubectl rollout restart`` does."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    patch = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {"kubectl.kubernetes.io/restartedAt": now}
                }
            }
        }
    }
    clients.apps.patch_namespaced_deployment(name, namespace, patch)


def delete_pod(clients: Clients, name: str, namespace: str) -> None:
    clients.core.delete_namespaced_pod(name, namespace)
