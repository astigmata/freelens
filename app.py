"""Freelens — application entry point."""

import logging

import dash

from freelens import config
from freelens.audit import init_audit
from freelens.auth import enforce_safe_bind, print_startup_banner, register_auth
from freelens.callbacks import register_callbacks
from freelens.security import register_security_headers
from freelens.terminal import register_terminal
from freelens.ui.layout import create_layout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    title="Kubernetes Explorer",
    # Required for the responsive CSS media queries to trigger on mobile devices.
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
app.layout = create_layout()
register_callbacks(app)
# Structured, immutable audit trail.
init_audit()
# Authentication + identity propagation + CSRF guard on every request.
register_auth(app.server)
# Defence-in-depth HTTP headers on every response.
register_security_headers(app.server)
# Interactive pod terminal (xterm.js <-> WebSocket <-> pod exec stream).
register_terminal(app.server)

# Exposed for WSGI servers (e.g. gunicorn freelens app:server).
server = app.server


if __name__ == "__main__":
    # Guardrail: never serve unauthenticated on a network-reachable address.
    enforce_safe_bind(config.HOST)
    print_startup_banner(config.HOST, config.PORT)
    # threaded=True so the terminal WebSocket runs alongside normal requests.
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)
