"""A real interactive terminal into pods, bridged over WebSocket.

Dash itself is request/response, so a genuine TTY shell can't live in a normal
callback. Instead we serve a standalone xterm.js page (``/terminal``) that the
Exec tab loads in an ``<iframe>``; that page opens a WebSocket back to this same
Flask server (``/ws/exec``), which is bridged to the Kubernetes pod-exec stream
running an interactive shell. The result is a real shell session (history, vim,
top, colours…), not one-shot command execution.
"""

import json
import logging
from urllib.parse import urlparse

from flask import Flask, Response, request
from kubernetes.stream import stream

from . import config
from .k8s.client import get_clients

log = logging.getLogger(__name__)

# Locked-down CSP for the terminal page: no remote code, assets served from this
# origin only, sockets to same origin (ws/wss). It can only be framed by the app.
_TERMINAL_CSP = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self' ws: wss:; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "frame-ancestors 'self'"
)

try:
    from flask_sock import Sock
except ImportError:  # pragma: no cover - terminal just stays disabled
    Sock = None


_TERMINAL_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Pod terminal</title>
<link rel="stylesheet" href="/assets/vendor/xterm.min.css"/>
<script src="/assets/vendor/xterm.min.js"></script>
<script src="/assets/vendor/xterm-addon-fit.min.js"></script>
<style>
  html, body { margin: 0; height: 100%; background: #15171a; }
  #term { height: 100%; width: 100%; padding: 6px; box-sizing: border-box; }
</style>
</head>
<body>
<div id="term"></div>
<script>
  const params = new URLSearchParams(window.location.search);
  const term = new Terminal({
    cursorBlink: true, fontSize: 13,
    fontFamily: 'SF Mono, JetBrains Mono, Fira Code, Consolas, monospace',
    theme: { background: '#15171a', foreground: '#e4e6eb' },
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(document.getElementById('term'));
  fit.fit();

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/exec?${params.toString()}`);
  const sendResize = () => {
    if (ws.readyState === 1) ws.send(JSON.stringify({type: 'resize', cols: term.cols, rows: term.rows}));
  };
  ws.onopen = () => { sendResize(); term.focus(); };
  ws.onmessage = (e) => term.write(e.data);
  ws.onclose = () => term.write('\\r\\n\\x1b[31m[session closed]\\x1b[0m\\r\\n');
  term.onData((d) => { if (ws.readyState === 1) ws.send(JSON.stringify({type: 'input', data: d})); });
  window.addEventListener('resize', () => { fit.fit(); sendResize(); });
</script>
</body>
</html>
"""


def register_terminal(server: Flask) -> bool:
    """Wire up the terminal page and its WebSocket. Returns False if disabled."""
    if Sock is None:
        log.warning("flask-sock is not installed; the pod terminal is disabled.")
        return False

    sock = Sock(server)

    @server.route("/terminal")
    def terminal_page():
        resp = Response(_TERMINAL_PAGE, mimetype="text/html")
        resp.headers["Content-Security-Policy"] = _TERMINAL_CSP
        return resp

    @sock.route("/ws/exec")
    def exec_socket(ws):
        # Defend against Cross-Site WebSocket Hijacking: a cross-origin page must
        # not be able to open a shell through a logged-in user's browser. Browsers
        # always send Origin on WebSocket handshakes, so a missing/foreign Origin
        # is rejected.
        if not _origin_allowed(request):
            log.warning("Rejected /ws/exec from disallowed origin: %r",
                        request.headers.get("Origin"))
            ws.send("Origin not allowed.\r\n")
            return

        namespace = request.args.get("namespace", "")
        pod = request.args.get("pod", "")
        container = request.args.get("container") or None
        if not pod or not namespace:
            ws.send("Missing pod/namespace.\r\n")
            return
        try:
            resp = stream(
                get_clients().core.connect_get_namespaced_pod_exec,
                pod,
                namespace,
                container=container,
                # Prefer bash, fall back to sh; a TTY makes it interactive.
                command=["/bin/sh", "-c", "exec /bin/bash || exec /bin/sh"],
                stderr=True,
                stdin=True,
                stdout=True,
                tty=True,
                _preload_content=False,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced into the terminal
            ws.send(f"Failed to open shell: {exc}\r\n")
            return
        _bridge(ws, resp)

    return True


def _origin_allowed(req) -> bool:
    """True when the WebSocket handshake's Origin is same-origin or allow-listed.

    A missing Origin is rejected: real browsers always send one on a WebSocket
    handshake, so its absence means a non-browser / forged client.
    """
    origin = req.headers.get("Origin")
    if not origin:
        return False
    if origin in config.ALLOWED_ORIGINS:
        return True
    # Same-origin: the Origin's host[:port] must match the request Host header.
    return urlparse(origin).netloc == req.host


def _bridge(ws, resp) -> None:
    """Pump bytes both ways between the browser socket and the pod exec stream."""
    from simple_websocket import ConnectionClosed

    try:
        while resp.is_open():
            resp.update(timeout=0.05)
            if resp.peek_stdout():
                ws.send(resp.read_stdout())
            if resp.peek_stderr():
                ws.send(resp.read_stderr())
            try:
                message = ws.receive(timeout=0)
            except ConnectionClosed:
                break
            if not message:
                continue
            try:
                event = json.loads(message)
            except (ValueError, TypeError):
                continue
            if event.get("type") == "input":
                resp.write_stdin(event.get("data", ""))
            elif event.get("type") == "resize":
                resp.write_channel(
                    4, json.dumps({"Width": event.get("cols", 80), "Height": event.get("rows", 24)})
                )
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001
            pass
