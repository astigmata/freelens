"""Port-forward tab: start a local listener into a pod/service, stop active ones.

Starting and stopping both bump ``forward-trigger``, which is an Input of the
detail-tab renderer, so the active-forwards table re-renders with the new state.
"""

import logging

from dash import ALL, Dash, Input, Output, State, ctx
from dash.exceptions import PreventUpdate

from ..audit import audit
from ..auth import active_clients
from ..k8s import operations as ops
from ..k8s.registry import resource_from_path
from ..portforward import MANAGER

log = logging.getLogger(__name__)


def register(app: Dash) -> None:
    @app.callback(
        Output("forward-result", "children"),
        Output("forward-trigger", "data"),
        Input("forward-start", "n_clicks"),
        State("forward-port", "value"),
        State("forward-local-port", "value"),
        State("selected-resource", "data"),
        State("url", "pathname"),
        State("forward-trigger", "data"),
        prevent_initial_call=True,
    )
    def start_forward(n_clicks, remote_port, local_port, selected, pathname, trigger):
        if not n_clicks or not selected or not remote_port:
            raise PreventUpdate

        descriptor = resource_from_path(pathname)
        name, namespace = selected["name"], selected.get("namespace", "")
        target = {"kind": descriptor.key, "name": name, "namespace": namespace}
        try:
            clients = active_clients()
            pod, pod_port = ops.resolve_forward_target(
                clients, descriptor.key, name, namespace, int(remote_port)
            )
            fwd = MANAGER.start(
                clients.core, descriptor.key, name, namespace, pod, pod_port,
                int(local_port or 0),
            )
            audit("portforward.start", target, "success", remote_port=int(remote_port),
                  pod=pod, pod_port=pod_port, address=fwd.address)
            result = f"✓ Forwarding {fwd.address} → {namespace}/{name}:{remote_port}"
        except Exception as exc:  # noqa: BLE001
            log.warning("port-forward start failed for %s/%s: %s", namespace, name, exc)
            audit("portforward.start", target, "failure",
                  remote_port=remote_port, error=str(exc))
            result = f"✗ Could not start port-forward: {exc}"
        return result, (trigger or 0) + 1

    @app.callback(
        Output("forward-result", "children", allow_duplicate=True),
        Output("forward-trigger", "data", allow_duplicate=True),
        Input({"type": "forward-stop", "index": ALL}, "n_clicks"),
        State("forward-trigger", "data"),
        prevent_initial_call=True,
    )
    def stop_forward(_clicks, trigger):
        triggered = ctx.triggered[0] if ctx.triggered else None
        # Ignore the initial mount where every stop button reports n_clicks=0.
        if not triggered or not triggered["value"]:
            raise PreventUpdate

        fwd = MANAGER.stop(ctx.triggered_id["index"])
        if fwd is None:
            raise PreventUpdate
        audit("portforward.stop",
              {"kind": fwd.kind, "name": fwd.name, "namespace": fwd.namespace},
              "success", remote_port=fwd.remote_port, address=fwd.address)
        return f"✓ Stopped forward {fwd.address}", (trigger or 0) + 1
