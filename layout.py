from dash import html, dcc, dash_table

def create_layout():
    return html.Div([
        # Barre latérale de navigation
        html.Div([
            html.Img(src="assets/k8s-logo.png", style={'width': '200px', 'margin': '10px auto', 'display': 'block'}),
            html.Div([
                html.Div("Cluster", className="sidebar-item"),
                html.Div("Nodes", className="sidebar-item"),
                html.Div("Workloads", className="sidebar-item", id="workloads-nav"),
                html.Div([
                    html.Div("Overview", id="workloads-overview", className="sidebar-subitem"),
                    html.Div("Pods", id="workloads-pods", className="sidebar-subitem active"),
                    html.Div("Deployments", id="workloads-deployments", className="sidebar-subitem"),
                    html.Div("DaemonSets", id="workloads-daemonsets", className="sidebar-subitem"),
                    html.Div("StatefulSets", id="workloads-statefulsets", className="sidebar-subitem"),
                    html.Div("ReplicaSets", id="workloads-replicasets", className="sidebar-subitem"),
                    html.Div("Replication Controllers", id="workloads-replicationcontrollers", className="sidebar-subitem"),
                    html.Div("Jobs", id="workloads-jobs", className="sidebar-subitem"),
                    html.Div("CronJobs", id="workloads-cronjobs", className="sidebar-subitem"),
                ], id="workloads-subitems", className="sidebar-subitems", style={'display': 'none'}),
                html.Div("Config", className="sidebar-item", id="config-nav"),
                html.Div([
                    html.Div("ConfigMaps", id="config-configmaps", className="sidebar-subitem"),
                    html.Div("Secrets", id="config-secrets", className="sidebar-subitem"),
                    html.Div("Resource Quotas", id="config-resourcequotas", className="sidebar-subitem"),
                    html.Div("Limit Ranges", id="config-limitranges", className="sidebar-subitem"),
                    html.Div("HPA", id="config-hpa", className="sidebar-subitem"),
                    html.Div("Pod Disruption Budgets", id="config-poddisruptionbudgets", className="sidebar-subitem"),
                    html.Div("Priority Classes", id="config-priorityclasses", className="sidebar-subitem"),
                    html.Div("Runtime Classes", id="config-runtimeclasses", className="sidebar-subitem"),
                    html.Div("Leases", id="config-leases", className="sidebar-subitem"),
                    html.Div("Mutating Webhook Configs", id="config-mutatingwebhookconfigs", className="sidebar-subitem"),
                    html.Div("Validating Webhook Configs", id="config-validatingwebhookconfigs", className="sidebar-subitem"),
                ], id="config-subitems", className="sidebar-subitems", style={'display': 'none'}),
                html.Div("Network", className="sidebar-item", id="network-nav"),
                html.Div([
                    html.Div("Services", id="network-services", className="sidebar-subitem"),
                    html.Div("Endpoints", id="network-endpoints", className="sidebar-subitem"),
                    html.Div("Ingresses", id="network-ingresses", className="sidebar-subitem"),
                    html.Div("Ingress Classes", id="network-ingressclasses", className="sidebar-subitem"),
                    html.Div("Network Policies", id="network-networkpolicies", className="sidebar-subitem"),
                    html.Div("Port Forwarding", id="network-portforwarding", className="sidebar-subitem"),
                ], id="network-subitems", className="sidebar-subitems", style={'display': 'none'}),
                html.Div("Storage", className="sidebar-item", id="storage-nav"),
                html.Div([
                    html.Div("Persistent Volume Claims", id="storage-persistentvolumeclaims", className="sidebar-subitem"),
                    html.Div("Persistent Volumes", id="storage-persistentvolumes", className="sidebar-subitem"),
                    html.Div("Storage Classes", id="storage-storageclasses", className="sidebar-subitem"),
                ], id="storage-subitems", className="sidebar-subitems", style={'display': 'none'}),
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
                html.H1(id="page-title", className="page-title"),
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
                        placeholder="Search...",
                        className="search-input"
                    ),
                    html.Button("Connect", id="connect-button", className="action-button"),
                    html.Button("Refresh", id="refresh-button", className="action-button"),
                    html.Div(id="connection-status", className="connection-status"),
                    html.Div(id='dummy-output', style={'display': 'none'})
                ], className="header-controls")
            ], className="page-header"),
            # Vue des Pods
            html.Div(id="pods-view", style={'display': 'block'}, children=[
                # Ajoutez le champ de recherche ici
                dcc.Input(
                    id="pods-search-input",
                    type="text",
                    placeholder="Search Pods...",
                    className="search-input"
                ),
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
                        style_header={'backgroundColor': '#2d2d2d', 'fontWeight': 'bold', 'border': '1px solid #444', 'color': '#e0e0e0'},
                        style_cell={'textAlign': 'left', 'padding': '8px', 'border': '1px solid #444', 'backgroundColor': '#1e1e1e', 'color': '#e0e0e0'},
                        style_data_conditional=[
                            {'if': {'row_index': 'odd'}, 'backgroundColor': '#2d2d2d'},
                            {'if': {'filter_query': '{status} = "Running"'}, 'color': '#4caf50'},
                            {'if': {'filter_query': '{status} = "Pending"'}, 'color': '#ff9800'},
                            {'if': {'filter_query': '{status} = "Failed"'}, 'color': '#f44336'}
                        ],
                        page_size=15,
                        style_table={'overflowX': 'auto'},
                        row_selectable='single'
                    )
                ], className="table-container"),
                html.Div(id="pod-details", className="pod-details"),
            ]),

            # Vue des Deployments
            html.Div(id="deployments-view", style={'display': 'none'}, children=[
                # Ajoutez le champ de recherche ici
                dcc.Input(
                    id="deployments-search-input",
                    type="text",
                    placeholder="Search Deployments...",
                    className="search-input"
                ),
                html.Div([
                    dash_table.DataTable(
                        id='deployments-table',
                        columns=[
                            {"name": "Name", "id": "name"},
                            {"name": "Namespace", "id": "namespace"},
                            {"name": "Replicas", "id": "replicas"},
                            {"name": "Up-to-date", "id": "up_to_date"},
                            {"name": "Available", "id": "available"},
                            {"name": "Age", "id": "age"},
                            {"name": "Strategy", "id": "strategy"},
                            {"name": "Labels", "id": "labels"}
                        ],
                        data=[],
                        style_header={'backgroundColor': '#2d2d2d', 'fontWeight': 'bold', 'border': '1px solid #444', 'color': '#e0e0e0'},
                        style_cell={'textAlign': 'left', 'padding': '8px', 'border': '1px solid #444', 'backgroundColor': '#1e1e1e', 'color': '#e0e0e0'},
                        style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#2d2d2d'}],
                        page_size=15,
                        style_table={'overflowX': 'auto'},
                        row_selectable='single'
                    )
                ], className="table-container"),
                html.Div(id="deployment-details", className="deployment-details"),
            ]),

            # Vue des Daemon sets
            html.Div(id="daemon-set-view", style={'display': 'none'}, children=[
                # Ajoutez le champ de recherche ici
                dcc.Input(
                    id="daemon-sets-search-input",
                    type="text",
                    placeholder="Search DaemonSets...",
                    className="search-input"
                ),
                html.Div([
                    dash_table.DataTable(
                        id='daemon-sets-table',
                        columns=[
                            {"name": "Name", "id": "name"},
                            {"name": "Namespace", "id": "namespace"},
                            {"name": "Replicas", "id": "replicas"},
                            {"name": "Up-to-date", "id": "up_to_date"},
                            {"name": "Available", "id": "available"},
                            {"name": "Age", "id": "age"},
                            {"name": "Strategy", "id": "strategy"},
                            {"name": "Labels", "id": "labels"}
                        ],
                        data=[],
                        style_header={'backgroundColor': '#2d2d2d', 'fontWeight': 'bold', 'border': '1px solid #444',
                                      'color': '#e0e0e0'},
                        style_cell={'textAlign': 'left', 'padding': '8px', 'border': '1px solid #444',
                                    'backgroundColor': '#1e1e1e', 'color': '#e0e0e0'},
                        style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#2d2d2d'}],
                        page_size=15,
                        style_table={'overflowX': 'auto'},
                        row_selectable='single'
                    )
                ], className="table-container"),
                html.Div(id="daemon-set-details", className="daemon-set-details"),
            ]),

            # Stockage des données
            dcc.Store(id='pods-data-store'),
            dcc.Store(id='deployments-data-store'),
            dcc.Store(id='daemon-sets-data-store'),
            dcc.Store(id='workloads-menu-state', data={'open': False}),
            dcc.Store(id='config-menu-state', data={'open': False}),
            dcc.Store(id='network-menu-state', data={'open': False}),
            dcc.Store(id='storage-menu-state', data={'open': False}),
        ], className="main-content")
    ], className="app-container")