"""Reusable view components rendered from a resource descriptor.

The single ``render_details`` builder replaces the duplicated, hand-written
``get_pod_details`` / ``get_deployment_details`` HTML, and the YAML / logs /
action builders are likewise generic across resource types.
"""

from dash import dcc, html

from ..k8s import operations as ops
from ..k8s.client import get_clients
from ..k8s.registry import DetailField, ResourceDescriptor, get_object

_STATUS_CLASS = {
    "Running": "status-running",
    "Ready": "status-running",
    "Active": "status-running",
    "Bound": "status-running",
    "Pending": "status-pending",
    "Terminating": "status-pending",
    "Failed": "status-failed",
    "NotReady": "status-failed",
}


def _render_field(field: DetailField, obj) -> html.Div:
    value = field.accessor(obj)

    if field.kind == "list":
        items = value if isinstance(value, list) else [str(value)]
        content = html.Ul([html.Li(str(item)) for item in items], className="detail-list")
    elif field.kind == "status":
        status_class = _STATUS_CLASS.get(str(value), "")
        content = html.Span(str(value), className=f"detail-value {status_class}".strip())
    else:
        content = html.Span(str(value), className="detail-value")

    return html.Div(
        [html.Span(f"{field.label}: ", className="detail-label"), content],
        className="detail-row",
    )


def render_details(descriptor: ResourceDescriptor, obj) -> html.Div:
    return html.Div(
        [html.H3(f"{descriptor.label.rstrip('s')}: {obj.metadata.name}")]
        + [_render_field(field, obj) for field in descriptor.detail_fields]
    )


def render_yaml(descriptor: ResourceDescriptor, name: str, namespace: str) -> html.Pre:
    obj = get_object(descriptor, name, namespace)
    return html.Pre(ops.to_yaml(obj), className="yaml-view")


def render_logs(descriptor: ResourceDescriptor, name: str, namespace: str) -> html.Div:
    """Logs tab scaffold: a container selector, a reload button and an output pane."""
    containers = ops.list_containers(get_clients(), name, namespace)
    return html.Div(
        [
            html.Div(
                [
                    dcc.Dropdown(
                        id="log-container",
                        options=[{"label": c, "value": c} for c in containers],
                        value=containers[0] if containers else None,
                        clearable=False,
                        className="namespace-selector",
                    ),
                    html.Button("Reload logs", id="log-refresh", n_clicks=0, className="action-button"),
                ],
                className="logs-controls",
            ),
            html.Pre(id="log-output", className="logs-view"),
        ]
    )


def details_placeholder(descriptor: ResourceDescriptor) -> str:
    noun = descriptor.label.rstrip("s").lower()
    return f"Select a {noun} to see its details"


# --------------------------------------------------------------------------- #
# Helm release rendering (helm is CLI-driven, not part of the registry).
# --------------------------------------------------------------------------- #
def render_helm_actions(release: dict) -> list:
    """Action bar for a selected Helm release: rollback (+ revision) and uninstall."""
    name = release.get("name", "")
    return [
        html.Span(f"{name}", className="detail-target"),
        dcc.Input(
            id="helm-rollback-rev",
            type="number",
            min=1,
            placeholder="rev",
            className="action-value",
        ),
        html.Button(
            "Rollback",
            id={"type": "helm-action", "index": "rollback"},
            n_clicks=0,
            className="action-button",
        ),
        html.Button(
            "Uninstall",
            id={"type": "helm-action", "index": "uninstall"},
            n_clicks=0,
            className="action-button destructive",
        ),
    ]


def render_helm_values(values_yaml: str) -> html.Pre:
    return html.Pre(values_yaml or "(no values)", className="yaml-view")


def render_helm_manifest(manifest_yaml: str) -> html.Pre:
    return html.Pre(manifest_yaml or "(empty manifest)", className="yaml-view")


def render_helm_history(history: list) -> html.Div:
    if not history:
        return html.Div("No revision history.")
    rows = [
        html.Div(
            [
                html.Span(f"Revision {h.get('revision')}", className="detail-label"),
                html.Span(
                    f"{h.get('status', '')} — {h.get('chart', '')} "
                    f"(app {h.get('app_version', 'N/A')}) — {h.get('updated', '')}",
                    className="detail-value",
                ),
            ],
            className="detail-row",
        )
        for h in reversed(history)
    ]
    return html.Div(rows)


def helm_placeholder() -> str:
    return "Select a release to see its values, history and manifest"


def render_actions(descriptor: ResourceDescriptor, name: str) -> list:
    """Action bar: a scale input (if applicable) plus a button per action."""
    if not descriptor.actions or not name:
        return []

    children: list = [html.Span(f"{name}", className="detail-target")]
    for action in descriptor.actions:
        if action.needs_value:
            children.append(
                dcc.Input(
                    id="action-value",
                    type="number",
                    min=0,
                    value=action.value_default,
                    className="action-value",
                )
            )
        css = "action-button destructive" if action.destructive else "action-button"
        children.append(
            html.Button(
                action.label,
                id={"type": "action-btn", "index": action.key},
                n_clicks=0,
                className=css,
            )
        )
    return children
