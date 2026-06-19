"""Navigation: collapsible sidebar groups and URL-driven view switching.

Two pattern-matching callbacks replace the four near-identical ``toggle_*_menu``
callbacks and the giant 30-output active-state callback of the original code.
"""

from dash import ALL, MATCH, Dash, Input, Output, State, ctx, no_update

from ..k8s.registry import resource_from_path
from ..ui.layout import BASE_CONDITIONAL

HELM_PATH = "/helm"
CRD_PATH = "/crd"
# Standalone pages that replace the resource explorer rather than reusing it.
STANDALONE_PATHS = (HELM_PATH, CRD_PATH)


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

    # Open/close the mobile sidebar drawer. The hamburger toggles it; clicking the
    # overlay or navigating to a new page closes it. On wide screens the CSS keeps
    # the sidebar visible regardless of the "open" class.
    @app.callback(
        Output("sidebar", "className"),
        Output("sidebar-overlay", "style"),
        Input("sidebar-toggle", "n_clicks"),
        Input("sidebar-overlay", "n_clicks"),
        Input("url", "pathname"),
        State("sidebar", "className"),
        prevent_initial_call=True,
    )
    def toggle_sidebar(_toggle, _overlay, _pathname, current):
        is_open = "open" in (current or "")
        # Only the hamburger flips it open; everything else closes it.
        is_open = not is_open if ctx.triggered_id == "sidebar-toggle" else False
        class_name = "sidebar open" if is_open else "sidebar"
        overlay = {"display": "block"} if is_open else {"display": "none"}
        return class_name, overlay

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
        Output("crd-view", "style"),
        Output({"type": "standalone-nav", "index": ALL}, "className"),
        Input("url", "pathname"),
        State({"type": "nav-link", "index": ALL}, "id"),
        State({"type": "standalone-nav", "index": ALL}, "id"),
    )
    def route(pathname, link_ids, standalone_ids):
        path = pathname or ""
        standalone_classes = [
            "sidebar-item active" if sid["index"] == path else "sidebar-item"
            for sid in standalone_ids
        ]

        def styles(active):
            hide, show = {"display": "none"}, {"display": "block"}
            return (
                show if active == "resource" else hide,
                show if active == HELM_PATH else hide,
                show if active == CRD_PATH else hide,
            )

        if path in STANDALONE_PATHS:
            # Hide the resource explorer; the page's own callbacks drive it.
            inactive = ["sidebar-subitem" for _ in link_ids]
            res_style, helm_style, crd_style = styles(path)
            return (
                inactive, no_update, no_update, no_update, no_update,
                res_style, helm_style, crd_style, standalone_classes,
            )

        descriptor = resource_from_path(pathname)
        classes = [
            "sidebar-subitem active"
            if link["index"] == descriptor.key
            else "sidebar-subitem"
            for link in link_ids
        ]
        conditional = BASE_CONDITIONAL + descriptor.table_conditional
        res_style, helm_style, crd_style = styles("resource")
        # Clear any active cell (selection) when switching resource.
        return (
            classes, descriptor.title, descriptor.table_columns(), conditional, None,
            res_style, helm_style, crd_style, standalone_classes,
        )
