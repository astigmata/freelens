"""Top-level page layout.

A single, persistent resource table and detail panel are reused for every
resource — the routing callback swaps their columns and data — instead of one
hard-coded ``<resource>-view`` block per resource type.
"""

from dash import dash_table, dcc, html

from ..config import TABLE_PAGE_SIZE
from ..k8s.helm_catalog import CATALOG
from ..k8s.registry import DEFAULT_RESOURCE, REGISTRY
from .sidebar import create_sidebar

# Colours come from CSS custom properties (see assets/styles.css) so the table
# follows the active light/dark theme; var() resolves in the inline styles
# DataTable injects.
_STYLE_HEADER = {
    "backgroundColor": "var(--table-header-bg)",
    "fontWeight": "700",
    "border": "none",
    "borderBottom": "1px solid var(--table-border)",
    "color": "var(--table-header-fg)",
    "textTransform": "uppercase",
    "fontSize": "11.5px",
    "letterSpacing": "0.05em",
    "padding": "12px 12px",
}
_STYLE_CELL = {
    "textAlign": "left",
    "padding": "11px 12px",
    "border": "none",
    "borderBottom": "1px solid var(--table-border)",
    "backgroundColor": "var(--table-cell-bg)",
    "color": "var(--table-cell-fg)",
    "fontSize": "13.5px",
    # Cap column widths and ellipsize so wide tables (e.g. Pods' 9 columns) fit
    # on screen instead of pushing the last columns out of view.
    "whiteSpace": "nowrap",
    "overflow": "hidden",
    "textOverflow": "ellipsis",
    "minWidth": "80px",
    "maxWidth": "240px",
}
_STYLE_FILTER = {"backgroundColor": "var(--filter-bg)", "color": "var(--filter-fg)"}
BASE_CONDITIONAL = [{"if": {"row_index": "odd"}, "backgroundColor": "var(--row-odd-bg)"}]

# Helm releases are not Kubernetes API objects, so they get their own fixed
# columns rather than being described by a ResourceDescriptor.
HELM_COLUMNS = [
    {"name": "Name", "id": "name"},
    {"name": "Namespace", "id": "namespace"},
    {"name": "Revision", "id": "revision"},
    {"name": "Status", "id": "status"},
    {"name": "Chart", "id": "chart"},
    {"name": "App Version", "id": "app_version"},
    {"name": "Updated", "id": "updated"},
]
HELM_CONDITIONAL = BASE_CONDITIONAL + [
    {"if": {"filter_query": '{status} = "deployed"'}, "color": "var(--success)"},
    {"if": {"filter_query": '{status} = "failed"'}, "color": "var(--danger)"},
    {"if": {"filter_query": '{status} = "pending-install"'}, "color": "var(--warning)"},
    {"if": {"filter_query": '{status} = "pending-upgrade"'}, "color": "var(--warning)"},
]


def _resource_table() -> dash_table.DataTable:
    default = REGISTRY[DEFAULT_RESOURCE]
    return dash_table.DataTable(
        id="resource-table",
        columns=default.table_columns(),
        data=[],
        style_header=_STYLE_HEADER,
        style_cell=_STYLE_CELL,
        style_filter=_STYLE_FILTER,
        style_data_conditional=BASE_CONDITIONAL + default.table_conditional,
        # Paginated: only one page of rows is rendered in the DOM, so wide
        # clusters (thousands of pods) stay responsive. All rows are still sent
        # and native sort/filter apply across the whole dataset; the row counter
        # above shows the full total.
        page_action="native",
        page_size=TABLE_PAGE_SIZE,
        style_table={"overflowX": "auto"},
        # Row detail is driven by clicking any cell (active_cell); the checkbox
        # column (row_selectable) is for bulk operations like multi-delete.
        sort_action="native",
        filter_action="native",
        row_selectable="multi",
        selected_rows=[],
        css=[{"selector": ".dash-cell", "rule": "cursor: pointer;"}],
    )


def _header() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.H1(id="page-title", className="page-title"),
                    html.Span(id="row-count", className="row-count"),
                ],
                className="page-title-group",
            ),
            html.Div(
                [
                    html.Div(id="cluster-context", className="cluster-context"),
                    html.Div(id="connection-status", className="status-badge"),
                    dcc.Dropdown(
                        id="namespace-dropdown",
                        options=[{"label": "All namespaces", "value": "all"}],
                        value="all",
                        clearable=False,
                        className="namespace-selector",
                    ),
                    dcc.Input(
                        id="search-input",
                        type="text",
                        placeholder="Search...",
                        className="search-input",
                    ),
                    html.Button("Refresh", id="refresh-button", n_clicks=0, className="action-button"),
                    dcc.Checklist(
                        id="autorefresh-toggle",
                        options=[{"label": " Auto", "value": "on"}],
                        value=[],
                        className="autorefresh-toggle",
                    ),
                    # Light/dark switch. Icon + actual switching are handled
                    # clientside (see app.py) so the theme applies instantly and
                    # persists across reloads without a server round-trip.
                    html.Button(
                        id="theme-toggle",
                        n_clicks=0,
                        className="theme-toggle",
                        title="Toggle light / dark theme",
                    ),
                ],
                className="header-controls",
            ),
        ],
        className="page-header",
    )


def _detail_panel() -> html.Div:
    return html.Div(
        [
            html.Div(id="detail-actions", className="detail-actions"),
            html.Div(id="action-result", className="action-result"),
            dcc.ConfirmDialog(id="action-confirm"),
            dcc.Tabs(
                id="detail-tabs",
                value="overview",
                className="detail-tabs",
                children=[
                    dcc.Tab(label="Overview", value="overview", className="detail-tab"),
                    dcc.Tab(label="YAML", value="yaml", className="detail-tab"),
                    dcc.Tab(label="Logs", value="logs", className="detail-tab"),
                    dcc.Tab(label="Exec", value="exec", className="detail-tab"),
                    dcc.Tab(label="Forward", value="forward", className="detail-tab"),
                ],
            ),
            html.Div(id="resource-details", className="pod-details"),
        ],
        className="detail-panel",
    )


# --------------------------------------------------------------------------- #
# Helm view — a self-contained page shown only on the /helm route.
# --------------------------------------------------------------------------- #
def _helm_table() -> dash_table.DataTable:
    return dash_table.DataTable(
        id="helm-table",
        columns=HELM_COLUMNS,
        data=[],
        style_header=_STYLE_HEADER,
        style_cell=_STYLE_CELL,
        style_filter=_STYLE_FILTER,
        style_data_conditional=HELM_CONDITIONAL,
        page_size=TABLE_PAGE_SIZE,
        style_table={"overflowX": "auto"},
        sort_action="native",
        filter_action="native",
        css=[{"selector": ".dash-cell", "rule": "cursor: pointer;"}],
    )


def _helm_field(label: str, control) -> html.Div:
    return html.Div(
        [html.Label(label, className="helm-field-label"), control],
        className="helm-field",
    )


def _helm_deploy_form() -> html.Div:
    return html.Div(
        [
            html.H3("Deploy a chart"),
            _helm_field(
                "Popular charts",
                dcc.Dropdown(
                    id="helm-catalog",
                    options=[
                        {"label": f"{e.label} — {e.description}", "value": e.key}
                        for e in CATALOG
                    ],
                    placeholder="Pick a known chart to pre-fill the form…",
                    className="crd-selector",
                ),
            ),
            html.Div(
                [
                    _helm_field(
                        "Release name",
                        dcc.Input(id="helm-f-release", type="text",
                                  placeholder="my-release", className="search-input"),
                    ),
                    _helm_field(
                        "Chart",
                        dcc.Input(id="helm-f-chart", type="text",
                                  placeholder="repo/chart, oci://… or chart name", className="search-input"),
                    ),
                    _helm_field(
                        "Repo URL (optional)",
                        dcc.Input(id="helm-f-repo", type="text",
                                  placeholder="https://charts.example.com", className="search-input"),
                    ),
                    _helm_field(
                        "Version",
                        dcc.Input(id="helm-f-version", type="text",
                                  placeholder="latest", className="search-input"),
                    ),
                    _helm_field(
                        "Namespace",
                        dcc.Input(id="helm-f-namespace", type="text",
                                  placeholder="default", className="search-input"),
                    ),
                ],
                className="helm-form-row",
            ),
            dcc.Checklist(
                id="helm-f-createns",
                options=[{"label": " Create namespace if missing", "value": "yes"}],
                value=["yes"],
                className="autorefresh-toggle",
            ),
            _helm_field(
                "Values (YAML, optional)",
                dcc.Textarea(id="helm-f-values", placeholder="key: value",
                             className="helm-values-input"),
            ),
            html.Div(
                [html.Button("Install", id="helm-install-btn", n_clicks=0,
                             className="action-button")],
                className="detail-actions",
            ),
            html.Div(id="helm-install-result", className="action-result"),
        ],
        id="helm-deploy-form",
        className="pod-details",
        style={"display": "none"},
    )


def _helm_detail_panel() -> html.Div:
    return html.Div(
        [
            html.Div(id="helm-detail-actions", className="detail-actions"),
            html.Div(id="helm-action-result", className="action-result"),
            dcc.ConfirmDialog(id="helm-confirm"),
            dcc.Tabs(
                id="helm-tabs",
                value="values",
                className="detail-tabs",
                children=[
                    dcc.Tab(label="Values", value="values", className="detail-tab"),
                    dcc.Tab(label="History", value="history", className="detail-tab"),
                    dcc.Tab(label="Manifest", value="manifest", className="detail-tab"),
                ],
            ),
            html.Div(id="helm-detail-body", className="pod-details"),
        ],
        className="detail-panel",
    )


def _helm_view() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H1("Helm Releases", className="page-title"),
                            html.Span(id="helm-row-count", className="row-count"),
                        ],
                        className="page-title-group",
                    ),
                    html.Div(
                        [
                            html.Button("Deploy chart", id="helm-deploy-toggle",
                                        n_clicks=0, className="action-button"),
                            html.Button("Refresh", id="helm-refresh",
                                        n_clicks=0, className="action-button"),
                            dcc.Checklist(
                                id="helm-autorefresh-toggle",
                                options=[{"label": " Auto", "value": "on"}],
                                value=[],
                                className="autorefresh-toggle",
                            ),
                        ],
                        className="header-controls",
                    ),
                ],
                className="page-header",
            ),
            html.Div(id="helm-status", className="action-result"),
            _helm_deploy_form(),
            dcc.Loading(
                html.Div(_helm_table(), className="table-container"),
                type="default",
            ),
            _helm_detail_panel(),
            dcc.Store(id="helm-selected"),
            dcc.Store(id="helm-pending"),
            dcc.Store(id="helm-refresh-trigger", data=0),
            # Auto-refresh for the release list; disabled until toggled on.
            dcc.Interval(id="helm-interval", interval=5000, disabled=True),
        ],
        id="helm-view",
        style={"display": "none"},
    )


# --------------------------------------------------------------------------- #
# Custom Resources view — discovers CRDs at runtime and lists their instances.
# --------------------------------------------------------------------------- #
CRD_COLUMNS = [
    {"name": "Name", "id": "name"},
    {"name": "Namespace", "id": "namespace"},
    {"name": "Age", "id": "age"},
]


def _crd_table() -> dash_table.DataTable:
    return dash_table.DataTable(
        id="crd-table",
        columns=CRD_COLUMNS,
        data=[],
        style_header=_STYLE_HEADER,
        style_cell=_STYLE_CELL,
        style_filter=_STYLE_FILTER,
        style_data_conditional=BASE_CONDITIONAL,
        page_size=TABLE_PAGE_SIZE,
        style_table={"overflowX": "auto"},
        sort_action="native",
        filter_action="native",
        css=[{"selector": ".dash-cell", "rule": "cursor: pointer;"}],
    )


def _crd_view() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H1("Custom Resources", className="page-title"),
                            html.Span(id="crd-row-count", className="row-count"),
                        ],
                        className="page-title-group",
                    ),
                    html.Div(
                        [
                            dcc.Dropdown(
                                id="crd-select",
                                placeholder="Select a resource type…",
                                className="crd-selector",
                            ),
                            html.Button("Refresh", id="crd-refresh",
                                        n_clicks=0, className="action-button"),
                        ],
                        className="header-controls",
                    ),
                ],
                className="page-header",
            ),
            html.Div(id="crd-status", className="action-result"),
            dcc.Loading(
                html.Div(_crd_table(), className="table-container"),
                type="default",
            ),
            html.Div(
                [html.Div(id="crd-detail-body", className="pod-details")],
                className="detail-panel",
            ),
            dcc.Store(id="crd-selected"),
        ],
        id="crd-view",
        style={"display": "none"},
    )


def create_layout() -> html.Div:
    return html.Div(
        [
            dcc.Location(id="url", refresh=False),
            # Fires once on page load to populate the namespace dropdown / context.
            dcc.Interval(id="init-load", interval=200, max_intervals=1),
            # Drives auto-refresh; disabled until the user toggles it on.
            dcc.Interval(id="refresh-interval", interval=5000, disabled=True),
            # Bumped after a write action to force a data reload.
            dcc.Store(id="refresh-trigger", data=0),
            dcc.Store(id="selected-resource"),
            dcc.Store(id="action-pending"),
            # Bumped after a port-forward starts/stops to re-render the Forward tab.
            dcc.Store(id="forward-trigger", data=0),
            # Mobile drawer controls (hidden on wide screens via CSS).
            html.Button("☰", id="sidebar-toggle", className="sidebar-toggle", n_clicks=0),
            html.Div(id="sidebar-overlay", className="sidebar-overlay", n_clicks=0),
            create_sidebar(),
            html.Div(
                [
                    # Resource explorer (shown for every /r/<resource> route).
                    html.Div(
                        [
                            _header(),
                            # Bulk actions on checkbox-selected rows.
                            html.Div(
                                [
                                    html.Button(
                                        id="bulk-delete-btn",
                                        n_clicks=0,
                                        className="action-button destructive",
                                        style={"display": "none"},
                                    ),
                                    html.Span(id="bulk-result", className="action-result"),
                                ],
                                className="bulk-toolbar",
                            ),
                            dcc.ConfirmDialog(id="bulk-confirm"),
                            dcc.Store(id="bulk-pending"),
                            dcc.Loading(
                                html.Div(_resource_table(), className="table-container"),
                                type="default",
                            ),
                            _detail_panel(),
                        ],
                        id="resource-view",
                    ),
                    # Helm releases (shown only on /helm).
                    _helm_view(),
                    # Custom resources (shown only on /crd).
                    _crd_view(),
                ],
                className="main-content",
            ),
        ],
        className="app-container",
    )
