"""Custom Resources page: discover CRDs, list instances, show their manifests.

CRDs are discovered live (a freshly-installed operator like metallb shows up
without restarting the app) and their instances are read as plain dicts via the
dynamic CustomObjectsApi, so this page does not go through the registry.
"""

import json
import logging

from dash import Dash, Input, Output, State, html
from dash.exceptions import PreventUpdate

from ..k8s import crd
from ..k8s import operations as ops
from ..k8s.client import get_clients
from ..ui.layout import CRD_COLUMNS

log = logging.getLogger(__name__)

CRD_PATH = "/crd"


def register(app: Dash) -> None:
    @app.callback(
        Output("crd-select", "options"),
        Input("url", "pathname"),
        Input("crd-refresh", "n_clicks"),
    )
    def populate_crds(pathname, _refresh):
        if (pathname or "") != CRD_PATH:
            raise PreventUpdate
        try:
            crds = crd.list_crds(get_clients())
        except Exception as exc:  # noqa: BLE001 — surfaced as an empty dropdown
            log.warning("Could not list CRDs: %s", exc)
            return []
        return [
            {
                "label": f"{c['kind']}  ·  {c['group']}/{c['version']}",
                "value": json.dumps(c),
            }
            for c in crds
        ]

    @app.callback(
        Output("crd-table", "data"),
        Output("crd-table", "columns"),
        Output("crd-table", "active_cell"),
        Output("crd-row-count", "children"),
        Output("crd-status", "children"),
        Input("crd-select", "value"),
        Input("crd-refresh", "n_clicks"),
    )
    def load_instances(value, _refresh):
        if not value:
            raise PreventUpdate
        meta = json.loads(value)

        columns = [{"name": "Name", "id": "name"}]
        if meta["namespaced"]:
            columns.append({"name": "Namespace", "id": "namespace"})
        columns.append({"name": "Age", "id": "age"})

        try:
            items = crd.list_instances(
                get_clients(), meta["group"], meta["version"],
                meta["plural"], meta["namespaced"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not list %s: %s", meta["plural"], exc)
            return [], columns, None, "", f"Error: {exc}"

        rows = crd.to_rows(items)
        count = f"{len(rows)} item{'s' if len(rows) != 1 else ''}"
        return rows, columns, None, count, ""

    @app.callback(
        Output("crd-selected", "data"),
        Input("crd-table", "active_cell"),
        State("crd-table", "derived_viewport_data"),
    )
    def select_instance(active_cell, viewport):
        if not active_cell or not viewport:
            return None
        try:
            row = viewport[active_cell["row"]]
        except (IndexError, KeyError):
            return None
        return {"name": row.get("name"), "namespace": row.get("namespace", "")}

    @app.callback(
        Output("crd-detail-body", "children"),
        Input("crd-selected", "data"),
        State("crd-select", "value"),
    )
    def render_instance(selected, value):
        if not selected or not value:
            return "Select a custom resource to see its manifest"
        meta = json.loads(value)
        try:
            obj = crd.get_instance(
                get_clients(), meta["group"], meta["version"], meta["plural"],
                meta["namespaced"], selected.get("namespace", ""), selected["name"],
            )
            return html.Pre(ops.to_yaml(obj), className="yaml-view")
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read custom resource %s: %s", selected["name"], exc)
            return html.Div(f"Error: {exc}", className="detail-error")
