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

# Set the saved (or system-preferred) theme on <html> *before* the body paints
# so there is no flash of the wrong palette. The header toggle persists the
# choice to localStorage under the same key.
app.index_string = """<!DOCTYPE html>
<html>
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<script>
(function () {
  try {
    var saved = localStorage.getItem('freelens-theme');
    var theme = saved
      || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
  } catch (e) {
    document.documentElement.setAttribute('data-theme', 'light');
  }
})();
</script>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""

app.layout = create_layout()
register_callbacks(app)

# Light/dark toggle, handled entirely in the browser: flip the <html> data-theme
# attribute (which re-points every CSS custom property), persist it, and return
# the matching icon for the button. On the initial call (n_clicks falsy) we only
# sync the icon to the already-applied theme without flipping it.
app.clientside_callback(
    """
    function (n) {
        var root = document.documentElement;
        var current = root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        var next = current;
        if (n) {
            next = current === 'dark' ? 'light' : 'dark';
            root.setAttribute('data-theme', next);
            try { localStorage.setItem('freelens-theme', next); } catch (e) {}
        }
        // Show the icon of the theme you'd switch *to*.
        return next === 'dark' ? '☀️' : '☾';
    }
    """,
    dash.Output("theme-toggle", "children"),
    dash.Input("theme-toggle", "n_clicks"),
)
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
