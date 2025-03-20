from dash import html, dcc, dash_table

def create_layout():
    return html.Div([
        # Barre latérale de navigation
        html.Div([
            html.Img(src="assets/k8s-logo.png", style={'width': '200px', 'margin': '10px auto', 'display': 'block'}),
            html.Div([
                html.Div("Cluster", className="sidebar-item active"),
                html.Div("Nodes", className="sidebar-item"),
                html.Div("Workloads", className="sidebar-item", id="workloads-nav"),
                html.Div([
                    html.Div("Overview", className="sidebar-subitem"),
                    html.Div("Pods", className="sidebar-subitem active"),
                    html.Div("Deployments", className="sidebar-subitem"),
                    html.Div("DaemonSets", className="sidebar-subitem"),
                    html.Div("StatefulSets", className="sidebar-subitem"),
                    html.Div("ReplicaSets", className="sidebar-subitem"),
                    html.Div("Replication Controllers", className="sidebar-subitem"),
                    html.Div("Jobs", className="sidebar-subitem"),
                    html.Div("CronJobs", className="sidebar-subitem"),
                ], id="workloads-subitems", className="sidebar-subitems", style={'display': 'none'}),
                html.Div("Config", className="sidebar-item", id="config-nav"),
                html.Div([
                    html.Div("ConfigMaps", className="sidebar-subitem"),
                    html.Div("Secrets", className="sidebar-subitem active"),
                    html.Div("Resource Quotas", className="sidebar-subitem"),
                    html.Div("Limit Ranges", className="sidebar-subitem"),
                    html.Div("HPA", className="sidebar-subitem"),
                    html.Div("Pod Disruption Budgets", className="sidebar-subitem"),
                    html.Div("Priority Classes", className="sidebar-subitem"),
                    html.Div("Runtime Classes", className="sidebar-subitem"),
                    html.Div("Leases", className="sidebar-subitem"),
                    html.Div("Mutating Webhook Configs", className="sidebar-subitem"),
                    html.Div("Validating Webhook Configs", className="sidebar-subitem"),
                ], id="config-subitems", className="sidebar-subitems", style={'display': 'none'}),
                html.Div("Network", className="sidebar-item", id="network-nav"),
                html.Div([
                    html.Div("Services", className="sidebar-subitem"),
                    html.Div("Endpoints", className="sidebar-subitem"),
                    html.Div("Ingresses", className="sidebar-subitem"),
                    html.Div("Ingress Classes", className="sidebar-subitem"),
                    html.Div("Network Policies", className="sidebar-subitem"),
                    html.Div("Port Forwarding", className="sidebar-subitem"),
                ], id="network-subitems", className="sidebar-subitems", style={'display': 'none'}),
                html.Div("Storage", className="sidebar-item"),
                html.Div("Namespace", className="sidebar-item"),
                html.Div("Events", className="sidebar-item"),
                html.Div("Helm", className="sidebar-item"),
                html.Div("Access Control", className="sidebar-item"),
                html.Div("Custom Resources", className="sidebar-item"),
            ], className="sidebar-nav")
        ], className="sidebar"),

        # Zone principale de contenu
        html.Div([
            # En-tête
            html.Div([
                html.H1("Pods", className="page-title"),
                html.Div([
                    dcc.Dropdown(
                        id='namespace-dropdown',
                        options=[
                            {'label': 'All namespaces', 'value': 'all'},
                            {'label': 'kube-system', 'value': 'kube-system'},
                            {'label': 'default', 'value': 'default'},
                            {'label': 'deluge', 'value': 'deluge'},
                        ],
                        value='all',
                        clearable=False,
                        className="namespace-selector"
                    ),
                    dcc.Input(
                        id="search-input",
                        type="text",
                        placeholder="Search Pods...",
                        className="search-input"
                    ),
                    html.Button("Connect", id="connect-button", className="action-button"),
                    html.Button("Refresh", id="refresh-button", className="action-button"),
                    html.Div(id="connection-status", className="connection-status")
                ], className="header-controls")
            ], className="page-header"),

            # Tableau des Pods
            html.Div([
                dash_table.DataTable(
                    id='pods-table',
                    columns=[
                        {"name": "Name", "id": "name"},
                        {"name": "Namespace", "id": "namespace"},
                        {"name": "Containers", "id": "containers"},
                        {"name": "Restarts", "id": "restarts"},
                        {"name": "Controlled By", "id": "controlled_by"},
                        {"name": "Node", "id": "node"},
                        {"name": "QoS", "id": "qos"},
                        {"name": "Age", "id": "age"},
                        {"name": "Status", "id": "status"}
                    ],
                    data=[],
                    style_header={
                        'backgroundColor': '#2d2d2d',
                        'fontWeight': 'bold',
                        'border': '1px solid #444',
                        'color': '#e0e0e0'
                    },
                    style_cell={
                        'textAlign': 'left',
                        'padding': '8px',
                        'border': '1px solid #444',
                        'backgroundColor': '#1e1e1e',
                        'color': '#e0e0e0'
                    },
                    style_data_conditional=[
                        {
                            'if': {'row_index': 'odd'},
                            'backgroundColor': '#2d2d2d'
                        },
                        {
                            'if': {'filter_query': '{status} = "Running"'},
                            'color': '#4caf50'
                        },
                        {
                            'if': {'filter_query': '{status} = "Pending"'},
                            'color': '#ff9800'
                        },
                        {
                            'if': {'filter_query': '{status} = "Failed"'},
                            'color': '#f44336'
                        }
                    ],
                    page_size=15,
                    style_table={'overflowX': 'auto'},
                    row_selectable='single'
                )
            ], className="table-container"),

            # Détails du Pod sélectionné
            html.Div(id="pod-details", className="pod-details"),

            # Stockage des données des pods
            dcc.Store(id='pods-data-store'),
            # Stockage de l'état des menus
            dcc.Store(id='workloads-menu-state', data={'open': False}),
            dcc.Store(id='config-menu-state', data={'open': False}),
            dcc.Store(id='network-menu-state', data={'open': False}),
        ], className="main-content")
    ], className="app-container")
