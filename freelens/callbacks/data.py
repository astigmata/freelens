"""Data loading: one generic callback feeds the table for any resource.

Replaces the per-resource ``update_*_data`` / ``filter_*`` callbacks (and their
duplicated, racy writes to ``connection-status``). Also drives the status badge,
row counter, active-context label and the auto-refresh interval.
"""

import logging

from dash import Dash, Input, Output
from dash.exceptions import PreventUpdate

from ..k8s.client import current_context, get_namespaces
from ..k8s.registry import list_rows, resource_from_path

log = logging.getLogger(__name__)


def register(app: Dash) -> None:
    @app.callback(
        Output("namespace-dropdown", "options"),
        Output("cluster-context", "children"),
        Input("init-load", "n_intervals"),
    )
    def initialise(_):
        context = current_context()
        context_label = f"Context: {context}" if context else "In-cluster / no context"
        options = [{"label": "All namespaces", "value": "all"}]
        try:
            options.extend({"label": ns, "value": ns} for ns in get_namespaces())
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not list namespaces: %s", exc)
        return options, context_label

    @app.callback(
        Output("refresh-interval", "disabled"),
        Input("autorefresh-toggle", "value"),
    )
    def toggle_autorefresh(value):
        return "on" not in (value or [])

    @app.callback(
        Output("resource-table", "data"),
        Output("connection-status", "children"),
        Output("connection-status", "className"),
        Output("row-count", "children"),
        Input("url", "pathname"),
        Input("namespace-dropdown", "value"),
        Input("refresh-button", "n_clicks"),
        Input("search-input", "value"),
        Input("refresh-interval", "n_intervals"),
        Input("refresh-trigger", "data"),
    )
    def load_resource(pathname, namespace, _refresh, search, _tick, _trigger):
        # The Helm page has its own table/loader; don't query the cluster for it.
        if (pathname or "") == "/helm":
            raise PreventUpdate
        descriptor = resource_from_path(pathname)
        rows, status = list_rows(descriptor, namespace or "all")
        if search:
            term = search.lower()
            rows = [row for row in rows if term in row.get("name", "").lower()]

        connected = status == "Connected"
        badge_class = "status-badge connected" if connected else "status-badge error"
        count = f"{len(rows)} item{'s' if len(rows) != 1 else ''}" if connected else ""
        return rows, status, badge_class, count
