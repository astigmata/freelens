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

from flask import Flask, Response, request
from kubernetes.stream import stream

from .k8s.client import get_clients

log = logging.getLogger(__name__)

try:
    from flask_sock import Sock
except ImportError:  # pragma: no cover - terminal just stays disabled
    Sock = None


_TERMINAL_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Pod terminal</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css"/>
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js"></script>
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
        return Response(_TERMINAL_PAGE, mimetype="text/html")

    @sock.route("/ws/exec")
    def exec_socket(ws):
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
