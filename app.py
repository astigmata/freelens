"""Freelens — application entry point."""

import logging

import dash

from freelens import config
from freelens.callbacks import register_callbacks
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

# Exposed for WSGI servers (e.g. gunicorn freelens app:server).
server = app.server


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
