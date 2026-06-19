"""Sidebar navigation, generated from the resource registry's MENU definition.

Expandable groups and their items are built with pattern-matching component ids so
a single callback can handle toggling and active-state highlighting, instead of one
hand-written callback per group.
"""

from dash import dcc, html

from ..k8s.registry import DEFAULT_RESOURCE, MENU, MenuGroup


def group_header_id(group: str) -> dict:
    return {"type": "group-header", "index": group}


def group_body_id(group: str) -> dict:
    return {"type": "group-body", "index": group}


def nav_link_id(key: str) -> dict:
    return {"type": "nav-link", "index": key}


def standalone_nav_id(href: str) -> dict:
    return {"type": "standalone-nav", "index": href}


def _render_item(item) -> html.Div:
    if item.implemented:
        active = " active" if item.key == DEFAULT_RESOURCE else ""
        return dcc.Link(
            item.label,
            href=f"/r/{item.key}",
            id=nav_link_id(item.key),
            className=f"sidebar-subitem{active}",
        )
    return html.Div(
        item.label,
        className="sidebar-subitem disabled",
        title="Not implemented yet",
    )


def _render_group(group: MenuGroup) -> list:
    if not group.items:
        if group.href:
            # Standalone, non-expandable entry that links to its own page.
            return [
                dcc.Link(
                    group.label,
                    href=group.href,
                    id=standalone_nav_id(group.href),
                    className="sidebar-item",
                )
            ]
        # Standalone entry that is not implemented yet.
        return [html.Div(group.label, className="sidebar-item disabled")]

    # A group is open by default if it contains the default resource.
    open_by_default = any(item.key == DEFAULT_RESOURCE for item in group.items)
    return [
        html.Div(
            group.label,
            id=group_header_id(group.label),
            className="sidebar-item",
            n_clicks=0,
        ),
        html.Div(
            [_render_item(item) for item in group.items],
            id=group_body_id(group.label),
            className="sidebar-subitems",
            style={"display": "block" if open_by_default else "none"},
        ),
    ]


def create_sidebar() -> html.Div:
    nav_children: list = []
    for group in MENU:
        nav_children.extend(_render_group(group))

    return html.Div(
        [
            html.Img(
                src="assets/k8s-logo.png",
                style={"width": "200px", "margin": "10px auto", "display": "block"},
            ),
            html.Div(nav_children, className="sidebar-nav"),
        ],
        id="sidebar",
        className="sidebar",
    )
