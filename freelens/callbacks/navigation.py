"""Navigation: collapsible sidebar groups and URL-driven view switching.

Two pattern-matching callbacks replace the four near-identical ``toggle_*_menu``
callbacks and the giant 30-output active-state callback of the original code.
"""

from dash import ALL, MATCH, Dash, Input, Output, State, no_update

from ..k8s.registry import resource_from_path
from ..ui.layout import BASE_CONDITIONAL

HELM_PATH = "/helm"


def register(app: Dash) -> None:
    # Expand / collapse a sidebar group (one callback for every group).
    @app.callback(
        Output({"type": "group-body", "index": MATCH}, "style"),
        Input({"type": "group-header", "index": MATCH}, "n_clicks"),
        State({"type": "group-body", "index": MATCH}, "style"),
        prevent_initial_call=True,
    )
    def toggle_group(n_clicks, style):
        style = dict(style or {})
        is_open = style.get("display") == "block"
        style["display"] = "none" if is_open else "block"
        return style

    # React to the active route: highlight the link, set the title, swap the
    # table's columns/conditional styling, and toggle between the resource
    # explorer and the dedicated Helm page.
    @app.callback(
        Output({"type": "nav-link", "index": ALL}, "className"),
        Output("page-title", "children"),
        Output("resource-table", "columns"),
        Output("resource-table", "style_data_conditional"),
        Output("resource-table", "active_cell"),
        Output("resource-view", "style"),
        Output("helm-view", "style"),
        Output({"type": "standalone-nav", "index": ALL}, "className"),
        Input("url", "pathname"),
        State({"type": "nav-link", "index": ALL}, "id"),
        State({"type": "standalone-nav", "index": ALL}, "id"),
    )
    def route(pathname, link_ids, standalone_ids):
        standalone_classes = [
            "sidebar-item active" if sid["index"] == pathname else "sidebar-item"
            for sid in standalone_ids
        ]

        if (pathname or "") == HELM_PATH:
            # Hide the resource explorer; the Helm callbacks own the Helm page.
            inactive = ["sidebar-subitem" for _ in link_ids]
            return (
                inactive, no_update, no_update, no_update, no_update,
                {"display": "none"}, {"display": "block"}, standalone_classes,
            )

        descriptor = resource_from_path(pathname)
        classes = [
            "sidebar-subitem active"
            if link["index"] == descriptor.key
            else "sidebar-subitem"
            for link in link_ids
        ]
        conditional = BASE_CONDITIONAL + descriptor.table_conditional
        # Clear any active cell (selection) when switching resource.
        return (
            classes, descriptor.title, descriptor.table_columns(), conditional, None,
            {"display": "block"}, {"display": "none"}, standalone_classes,
        )
