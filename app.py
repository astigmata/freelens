import dash
from dash import html, dcc, dash_table
from dash.dependencies import Input, Output, State
import pandas as pd
from kubernetes import client, config
import datetime

# Initialisation de l'application Dash
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Mise en page de l'application
app.layout = html.Div([
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

# Callback pour charger les données des pods dans le store
@app.callback(
    [Output('pods-data-store', 'data'),
     Output('connection-status', 'children')],
    [Input('connect-button', 'n_clicks'),
     Input('refresh-button', 'n_clicks'),
     Input('namespace-dropdown', 'value')],
    prevent_initial_call=True
)
def update_pods_data(connect_clicks, refresh_clicks, namespace):
    try:
        config.load_kube_config()
        api = client.CoreV1Api()
        if namespace == 'all':
            pods = api.list_pod_for_all_namespaces(watch=False)
        else:
            pods = api.list_namespaced_pod(namespace, watch=False)
        pods_data = []
        for pod in pods.items:
            creation_time = pod.metadata.creation_timestamp
            age = datetime.datetime.now(creation_time.tzinfo) - creation_time
            age_str = f"{age.days}d" if age.days > 0 else f"{int(age.seconds / 3600)}h"
            container_count = len(pod.spec.containers)
            container_ready = sum(1 for c in pod.status.container_statuses if c.ready) if pod.status.container_statuses else 0
            restarts = sum(c.restart_count for c in pod.status.container_statuses) if pod.status.container_statuses else 0
            controlled_by = f"{pod.metadata.owner_references[0].kind}/{pod.metadata.owner_references[0].name}" if pod.metadata.owner_references else "N/A"
            pods_data.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "containers": f"{container_ready}/{container_count}",
                "restarts": restarts,
                "controlled_by": controlled_by,
                "node": pod.spec.node_name if pod.spec.node_name else "N/A",
                "qos": pod.status.qos_class if pod.status.qos_class else "N/A",
                "age": age_str,
                "status": pod.status.phase
            })
        return pods_data, "Connecté"
    except Exception as e:
        return [], f"Erreur: {str(e)}"

# Callback pour filtrer les pods en fonction de la recherche
@app.callback(
    Output('pods-table', 'data'),
    [Input('search-input', 'value'),
     Input('pods-data-store', 'data')]
)
def filter_pods(search_term, pods_data):
    if pods_data is None:
        return []
    if search_term:
        filtered_data = [pod for pod in pods_data if search_term.lower() in pod['name'].lower()]
    else:
        filtered_data = pods_data
    return filtered_data

# Callback pour afficher les détails du pod sélectionné
@app.callback(
    Output('pod-details', 'children'),
    Input('pods-table', 'selected_rows'),
    State('pods-table', 'data')
)
def update_pod_details(selected_rows, data):
    if selected_rows:
        pod = data[selected_rows[0]]
        name = pod['name']
        namespace = pod['namespace']
        try:
            config.load_kube_config()
            api = client.CoreV1Api()
            pod_details = api.read_namespaced_pod(name, namespace)

            # Calcul de l'âge et de la date de création
            creation_time = pod_details.metadata.creation_timestamp
            age = datetime.datetime.now(creation_time.tzinfo) - creation_time
            age_str = f"{age.days}d {age.seconds//3600}h {age.seconds//60 % 60}m ago"
            created = creation_time.strftime("%Y-%m-%dT%H:%M:%S%z")

            # Labels et Annotations
            labels = [html.Li(f"{key}: {value}") for key, value in pod_details.metadata.labels.items()] if pod_details.metadata.labels else [html.Li("N/A")]
            annotations = [html.Li(f"{key}: {value}") for key, value in pod_details.metadata.annotations.items()] if pod_details.metadata.annotations else [html.Li("N/A")]

            # Controlled By
            controlled_by = pod['controlled_by']

            # Status avec classe CSS pour la couleur
            status_class = {
                "Running": "status-running",
                "Pending": "status-pending",
                "Failed": "status-failed"
            }.get(pod_details.status.phase, "")

            # Pod IP et Pod IPs
            pod_ip = pod_details.status.pod_ip if pod_details.status.pod_ip else "N/A"
            #pod_ips = ", ".join([ip.ip for ip in pod_details.status.pod_ips]) if pod_details.status.pod_ips else "N/A"

            # Service Account, Priority Class, QoS Class
            service_account = pod_details.spec.service_account_name if pod_details.spec.service_account_name else "N/A"
            priority_class = pod_details.spec.priority_class_name if pod_details.spec.priority_class_name else "N/A"
            qos_class = pod_details.status.qos_class if pod_details.status.qos_class else "N/A"

            # Conditions
            conditions = [html.Li(f"{condition.type}: {condition.status}") for condition in pod_details.status.conditions] if pod_details.status.conditions else [html.Li("N/A")]

            # Structure HTML pour les détails
            return html.Div([
                html.H3(f"Pod: {name}"),
                html.Div([
                    html.Span("Created: ", className="detail-label"),
                    html.Span(f"{age_str} {created}", className="detail-value"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Name: ", className="detail-label"),
                    html.Span(name, className="detail-value"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Namespace: ", className="detail-label"),
                    html.Span(namespace, className="detail-value"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Labels: ", className="detail-label"),
                    html.Ul(labels, className="detail-list"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Annotations: ", className="detail-label"),
                    html.Ul(annotations, className="detail-list"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Controlled By: ", className="detail-label"),
                    html.Span(controlled_by, className="detail-value"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Status: ", className="detail-label"),
                    html.Span(pod_details.status.phase, className=f"detail-value {status_class}"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Node: ", className="detail-label"),
                    html.Span(pod_details.spec.node_name if pod_details.spec.node_name else "N/A", className="detail-value"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Pod IP: ", className="detail-label"),
                    html.Span(pod_ip, className="detail-value"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Service Account: ", className="detail-label"),
                    html.Span(service_account, className="detail-value"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Priority Class: ", className="detail-label"),
                    html.Span(priority_class, className="detail-value"),
                ], className="detail-row"),
                html.Div([
                    html.Span("QoS Class: ", className="detail-label"),
                    html.Span(qos_class, className="detail-value"),
                ], className="detail-row"),
                html.Div([
                    html.Span("Conditions: ", className="detail-label"),
                    html.Ul(conditions, className="detail-list"),
                ], className="detail-row"),
            ], className="pod-details")

        except Exception as e:
            return html.Div(f"Erreur lors de la récupération des détails du pod: {str(e)}")
    else:
        return "Sélectionnez un pod pour voir les détails"

# Callback pour toggler le menu Workloads
@app.callback(
    [Output('workloads-subitems', 'style'),
     Output('workloads-menu-state', 'data')],
    Input('workloads-nav', 'n_clicks'),
    State('workloads-menu-state', 'data')
)
def toggle_workloads_menu(n_clicks, state):
    if n_clicks is None:
        return {'display': 'none'}, state
    open_state = not state['open']
    return {'display': 'block' if open_state else 'none'}, {'open': open_state}

# Callback pour toggler le menu Network
@app.callback(
    [Output('network-subitems', 'style'),
     Output('network-menu-state', 'data')],
    Input('network-nav', 'n_clicks'),
    State('network-menu-state', 'data')
)
def toggle_network_menu(n_clicks, state):
    if n_clicks is None:
        return {'display': 'none'}, state
    open_state = not state['open']
    return {'display': 'block' if open_state else 'none'}, {'open': open_state}

# Callback pour toggler le menu Config
@app.callback(
    [Output('config-subitems', 'style'),
     Output('config-menu-state', 'data')],
    Input('config-nav', 'n_clicks'),
    State('config-menu-state', 'data')
)
def toggle_config_menu(n_clicks, state):
    if n_clicks is None:
        return {'display': 'none'}, state
    open_state = not state['open']
    return {'display': 'block' if open_state else 'none'}, {'open': open_state}

# CSS personnalisé pour l'application
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Kubernetes Explorer</title>
        {%favicon%}
        {%css%}
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            .app-container {
                display: flex;
                height: 100vh;
            }
            .sidebar {
                width: 250px;
                background-color: #1e1e1e;
                color: #e0e0e0;
                overflow-y: auto;
                border-right: 1px solid #333;
            }
            .sidebar-item {
                padding: 12px 15px;
                cursor: pointer;
                display: flex;
                align-items: center;
            }
            .sidebar-item:hover {
                background-color: #2d2d2d;
            }
            .sidebar-item.active {
                background-color: #3e87e8;
                color: white;
            }
            .sidebar-subitems {
                padding-left: 20px;
                background-color: #1e1e1e;
            }
            .sidebar-subitem {
                padding: 8px 15px;
                cursor: pointer;
            }
            .sidebar-subitem:hover {
                background-color: #2d2d2d;
            }
            .sidebar-subitem.active {
                color: #3e87e8;
                font-weight: bold;
            }
            .main-content {
                flex: 1;
                padding: 20px;
                overflow-y: auto;
                background-color: #1e1e1e;
            }
            .page-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }
            .page-title {
                font-size: 24px;
                margin: 0;
                color: #e0e0e0;
            }
            .header-controls {
                display: flex;
                gap: 10px;
                align-items: center;
            }
            .namespace-selector {
                width: 200px;
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
            }
            .search-input {
                padding: 8px;
                border-radius: 4px;
                border: 1px solid #444;
                background-color: #2d2d2d;
                color: #e0e0e0;
                width: 200px;
            }
            .action-button {
                padding: 8px 16px;
                background-color: #3e87e8;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }
            .action-button:hover {
                background-color: #2d76d7;
            }
            .table-container {
                background-color: #1e1e1e;
                border-radius: 4px;
                border: 1px solid #333;
                width: 100%;
            }
            .pod-details {
                margin-top: 20px;
                background-color: #2d2d2d;
                border-radius: 4px;
                border: 1px solid #444;
                padding: 20px;
            }
            .detail-row {
                display: flex;
                align-items: center;
                margin-bottom: 10px;
            }
            .detail-label {
                font-weight: bold;
                color: #e0e0e0;
                width: 150px;
            }
            .detail-value {
                color: #e0e0e0;
            }
            .detail-list {
                margin: 0;
                padding-left: 20px;
            }
            .status-running {
                color: #4caf50;
            }
            .status-pending {
                color: #ff9800;
            }
            .status-failed {
                color: #f44336;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True, port=8050)