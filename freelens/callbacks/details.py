"""Detail panel: selection tracking, Overview / YAML / Logs tabs and log streaming."""

import logging

from dash import Dash, Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate

from ..k8s import operations as ops
from ..k8s.client import get_clients
from ..k8s.registry import get_object, resource_from_path
from ..ui.components import (
    details_placeholder,
    render_actions,
    render_details,
    render_exec,
    render_logs,
    render_yaml,
    terminal_src as render_terminal_src,
)


def _filter_lines(text: str, needle: str | None) -> str:
    if not needle:
        return text
    low = needle.lower()
    matches = [line for line in text.splitlines() if low in line.lower()]
    return "\n".join(matches) or "(no matching lines)"

log = logging.getLogger(__name__)


def register(app: Dash) -> None:
    @app.callback(
        Output("selected-resource", "data"),
        Input("resource-table", "active_cell"),
        State("resource-table", "derived_viewport_data"),
    )
    def track_selection(active_cell, viewport):
        # active_cell["row"] indexes the rows currently shown (after sort/filter/
        # paging), which is exactly what derived_viewport_data holds.
        if not active_cell or not viewport:
            return None
        try:
            row = viewport[active_cell["row"]]
        except (IndexError, KeyError):
            return None
        return {"name": row.get("name"), "namespace": row.get("namespace", "")}

    @app.callback(
        Output("detail-actions", "children"),
        Input("selected-resource", "data"),
        State("url", "pathname"),
    )
    def render_action_bar(selected, pathname):
        if not selected:
            return []
        descriptor = resource_from_path(pathname)
        return render_actions(descriptor, selected["name"])

    @app.callback(
        Output("resource-details", "children"),
        Input("detail-tabs", "value"),
        Input("selected-resource", "data"),
        Input("refresh-trigger", "data"),
        State("url", "pathname"),
    )
    def render_tab(tab, selected, _trigger, pathname):
        descriptor = resource_from_path(pathname)
        if not selected:
            return details_placeholder(descriptor)

        name, namespace = selected["name"], selected.get("namespace", "")
        try:
            if tab == "yaml":
                return render_yaml(descriptor, name, namespace)
            if tab == "logs":
                if not descriptor.supports_logs:
                    return html.Div("Logs are not available for this resource type.")
                return render_logs(descriptor, name, namespace)
            if tab == "exec":
                if not descriptor.supports_exec:
                    return html.Div("Exec is not available for this resource type.")
                return render_exec(descriptor, name, namespace)
            return render_details(descriptor, get_object(descriptor, name, namespace))
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not render %s for %s: %s", tab, name, exc)
            return html.Div(
                "Could not load this view. See the server logs for details.",
                className="detail-error",
            )

    @app.callback(
        Output("log-output", "children"),
        Input("log-container", "value"),
        Input("log-refresh", "n_clicks"),
        Input("log-filter", "value"),
        State("selected-resource", "data"),
    )
    def stream_logs(container, _refresh, log_filter, selected):
        if not selected or not container:
            raise PreventUpdate
        try:
            logs = ops.pod_logs(
                get_clients(), selected["name"], selected["namespace"], container
            )
            return _filter_lines(logs, log_filter) or "(no logs)"
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not fetch logs for %s: %s", selected.get("name"), exc)
            return "Could not fetch logs. See the server logs for details."

    @app.callback(
        Output("log-download", "data"),
        Input("log-download-btn", "n_clicks"),
        State("log-container", "value"),
        State("log-filter", "value"),
        State("selected-resource", "data"),
        prevent_initial_call=True,
    )
    def download_logs(n_clicks, container, log_filter, selected):
        if not n_clicks or not selected or not container:
            raise PreventUpdate
        logs = ops.pod_logs(
            get_clients(), selected["name"], selected["namespace"], container
        )
        logs = _filter_lines(logs, log_filter)
        filename = f"{selected['name']}_{container}.log"
        return dcc.send_string(logs, filename)

    @app.callback(
        Output("exec-terminal", "src"),
        Input("exec-container", "value"),
        Input("exec-reconnect", "n_clicks"),
        State("selected-resource", "data"),
        prevent_initial_call=True,
    )
    def update_terminal(container, reconnect, selected):
        if not selected:
            raise PreventUpdate
        src = render_terminal_src(selected.get("namespace", ""), selected["name"], container)
        # Append a nonce so "Reconnect" reloads the iframe even when the
        # container is unchanged.
        return f"{src}&_r={reconnect or 0}"
