"""Bulk actions on checkbox-selected rows (currently: multi-delete).

The resource table's ``row_selectable="multi"`` checkboxes feed this: a toolbar
button appears when rows are selected on a deletable resource, and goes through
the same confirm-then-execute pattern as single actions.
"""

import logging

from dash import Dash, Input, Output, State
from dash.exceptions import PreventUpdate

from ..k8s.client import get_clients
from ..k8s.registry import resource_from_path

log = logging.getLogger(__name__)


def register(app: Dash) -> None:
    @app.callback(
        Output("bulk-delete-btn", "children"),
        Output("bulk-delete-btn", "style"),
        Input("resource-table", "selected_rows"),
        State("url", "pathname"),
    )
    def update_bulk_bar(selected_rows, pathname):
        descriptor = resource_from_path(pathname)
        count = len(selected_rows or [])
        if count == 0 or descriptor.delete_fn is None:
            return "", {"display": "none"}
        return f"Delete {count} selected", {"display": "inline-flex"}

    @app.callback(
        Output("bulk-confirm", "message"),
        Output("bulk-confirm", "displayed"),
        Output("bulk-pending", "data"),
        Input("bulk-delete-btn", "n_clicks"),
        State("resource-table", "selected_rows"),
        State("resource-table", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def open_confirmation(n_clicks, selected_rows, data, pathname):
        if not n_clicks or not selected_rows:
            raise PreventUpdate
        descriptor = resource_from_path(pathname)
        if descriptor.delete_fn is None:
            raise PreventUpdate

        rows = [data[i] for i in selected_rows if i < len(data)]
        targets = [
            {"name": r.get("name"), "namespace": r.get("namespace", "")} for r in rows
        ]
        noun = descriptor.label.rstrip("s").lower()
        names = ", ".join(t["name"] for t in targets[:5])
        if len(targets) > 5:
            names += f" and {len(targets) - 5} more"
        message = f"Delete {len(targets)} {noun}(s)?\n\n{names}"
        return message, True, {"pathname": pathname, "targets": targets}

    @app.callback(
        Output("bulk-result", "children"),
        Output("refresh-trigger", "data", allow_duplicate=True),
        Output("resource-table", "selected_rows", allow_duplicate=True),
        Input("bulk-confirm", "submit_n_clicks"),
        State("bulk-pending", "data"),
        State("refresh-trigger", "data"),
        prevent_initial_call=True,
    )
    def execute(submit_n_clicks, pending, trigger):
        if not submit_n_clicks or not pending:
            raise PreventUpdate
        descriptor = resource_from_path(pending["pathname"])
        if descriptor.delete_fn is None:
            raise PreventUpdate

        clients = get_clients()
        ok, failures = 0, []
        for target in pending["targets"]:
            try:
                descriptor.delete_fn(clients, target["name"], target["namespace"])
                ok += 1
            except Exception as exc:  # noqa: BLE001 — collected and surfaced
                log.warning("Bulk delete of %s failed: %s", target["name"], exc)
                failures.append(f"{target['name']}: {exc}")

        result = f"✓ Deleted {ok}"
        if failures:
            result += f" — ✗ {len(failures)} failed: " + "; ".join(failures[:3])
        return result, (trigger or 0) + 1, []
