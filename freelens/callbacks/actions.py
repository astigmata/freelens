"""Write actions: action button -> confirmation dialog -> execution.

All mutating actions are funnelled through a single confirmation dialog so the
user always confirms before the cluster is changed.
"""

import logging

from dash import ALL, Dash, Input, Output, State, ctx
from dash.exceptions import PreventUpdate

from ..k8s.client import get_clients
from ..k8s.registry import resource_from_path

log = logging.getLogger(__name__)


def register(app: Dash) -> None:
    @app.callback(
        Output("action-confirm", "message"),
        Output("action-confirm", "displayed"),
        Output("action-pending", "data"),
        Input({"type": "action-btn", "index": ALL}, "n_clicks"),
        State("selected-resource", "data"),
        State("action-value", "value"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def open_confirmation(_clicks, selected, value, pathname):
        triggered = ctx.triggered[0] if ctx.triggered else None
        # Ignore the initial render where buttons mount with n_clicks=0.
        if not triggered or not triggered["value"] or not selected:
            raise PreventUpdate

        descriptor = resource_from_path(pathname)
        action = descriptor.action(ctx.triggered_id["index"])
        if action is None:
            raise PreventUpdate

        name, namespace = selected["name"], selected.get("namespace", "")
        noun = descriptor.label.rstrip("s").lower()
        message = f"{action.label} {noun} '{name}'"
        if namespace:
            message += f" in namespace '{namespace}'"
        if action.needs_value:
            message += f" — set {action.value_label} to {value}"
        message += "?"

        pending = {
            "action": action.key,
            "name": name,
            "namespace": namespace,
            "value": value,
            "pathname": pathname,
        }
        return message, True, pending

    @app.callback(
        Output("action-result", "children"),
        Output("refresh-trigger", "data"),
        Input("action-confirm", "submit_n_clicks"),
        State("action-pending", "data"),
        State("refresh-trigger", "data"),
        prevent_initial_call=True,
    )
    def execute(submit_n_clicks, pending, trigger):
        if not submit_n_clicks or not pending:
            raise PreventUpdate

        descriptor = resource_from_path(pending["pathname"])
        action = descriptor.action(pending["action"])
        if action is None:
            raise PreventUpdate

        try:
            action.fn(
                get_clients(), pending["name"], pending["namespace"], pending["value"]
            )
            result = f"✓ {action.label} '{pending['name']}' succeeded"
        except Exception as exc:  # noqa: BLE001
            log.warning("Action %s failed: %s", action.key, exc)
            result = f"✗ {action.label} failed: {exc}"

        return result, (trigger or 0) + 1
