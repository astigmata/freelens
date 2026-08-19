"""Bulk actions on checkbox-selected rows (currently: multi-delete).

The resource table's ``row_selectable="multi"`` checkboxes feed this: a toolbar
button appears when rows are selected on a deletable resource, and goes through
the same confirm-then-execute pattern as single actions.

Selection is tracked by stable row ids (``namespace/name``) rather than by
indices, so it keeps working across sorting, filtering and pagination.
"""

import logging

from dash import Dash, Input, Output, State
from dash.exceptions import PreventUpdate

from ..audit import audit
from ..auth import active_clients
from ..k8s.registry import resource_from_path

log = logging.getLogger(__name__)


def register(app: Dash) -> None:
    @app.callback(
        Output("bulk-delete-btn", "children"),
        Output("bulk-delete-btn", "style"),
        Input("resource-table", "selected_row_ids"),
        State("url", "pathname"),
    )
    def update_bulk_bar(selected_ids, pathname):
        descriptor = resource_from_path(pathname)
        count = len(selected_ids or [])
        if count == 0 or descriptor.delete_fn is None:
            return "", {"display": "none"}
        return f"Delete {count} selected", {"display": "inline-flex"}

    @app.callback(
        Output("bulk-confirm", "message"),
        Output("bulk-confirm", "displayed"),
        Output("bulk-pending", "data"),
        Input("bulk-delete-btn", "n_clicks"),
        State("resource-table", "selected_row_ids"),
        State("resource-table", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def open_confirmation(n_clicks, selected_ids, data, pathname):
        if not n_clicks or not selected_ids:
            raise PreventUpdate
        descriptor = resource_from_path(pathname)
        if descriptor.delete_fn is None:
            raise PreventUpdate

        by_id = {row.get("id"): row for row in data if row.get("id")}
        targets = [
            {"name": row["name"], "namespace": row.get("namespace", "")}
            for row_id in selected_ids
            if (row := by_id.get(row_id))
        ]
        if not targets:
            raise PreventUpdate
        noun = descriptor.label.rstrip("s").lower()
        names = ", ".join(t["name"] for t in targets[:5])
        if len(targets) > 5:
            names += f" and {len(targets) - 5} more"
        message = f"Delete {len(targets)} {noun}(s)?\n\n{names}"
        return message, True, {"pathname": pathname, "targets": targets}

    @app.callback(
        Output("bulk-result", "children"),
        Output("refresh-trigger", "data", allow_duplicate=True),
        Output("resource-table", "selected_row_ids", allow_duplicate=True),
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

        clients = active_clients()
        ok, failures = 0, []
        for target in pending["targets"]:
            try:
                descriptor.delete_fn(clients, target["name"], target["namespace"])
                audit(f"{descriptor.key}.delete",
                      {"kind": descriptor.key, "name": target["name"],
                       "namespace": target["namespace"]}, "success", bulk=True)
                ok += 1
            except Exception as exc:  # noqa: BLE001 — collected and surfaced
                log.warning("Bulk delete of %s failed: %s", target["name"], exc)
                audit(f"{descriptor.key}.delete",
                      {"kind": descriptor.key, "name": target["name"],
                       "namespace": target["namespace"]}, "failure",
                      bulk=True, error=str(exc))
                failures.append(f"{target['name']}: {exc}")

        result = f"✓ Deleted {ok}"
        if failures:
            result += f" — ✗ {len(failures)} failed: " + "; ".join(failures[:3])
        return result, (trigger or 0) + 1, []
