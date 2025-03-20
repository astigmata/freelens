from dash import Input, Output, State
from dash import html
from kubernetes_api import get_pods, get_pod_details, get_deployments, get_deployment_details
from dash import callback_context

def register_callbacks(app):
    # Liste de tous les IDs des sous-éléments
    all_subitem_ids = [
        "workloads-overview", "workloads-pods", "workloads-deployments", "workloads-daemonsets",
        "workloads-statefulsets", "workloads-replicasets", "workloads-replicationcontrollers",
        "workloads-jobs", "workloads-cronjobs",
        "config-configmaps", "config-secrets", "config-resourcequotas", "config-limitranges",
        "config-hpa", "config-poddisruptionbudgets", "config-priorityclasses", "config-runtimeclasses",
        "config-leases", "config-mutatingwebhookconfigs", "config-validatingwebhookconfigs",
        "network-services", "network-endpoints", "network-ingresses", "network-ingressclasses",
        "network-networkpolicies", "network-portforwarding",
        "storage-persistentvolumeclaims", "storage-persistentvolumes", "storage-storageclasses"
    ]

    # Callback pour mettre à jour la classe active et basculer entre les vues
    @app.callback(
        [Output(id, 'className') for id in all_subitem_ids] +
        [Output('pods-view', 'style'),
         Output('deployments-view', 'style'),
         Output('page-title', 'children')],
        [Input(id, 'n_clicks') for id in all_subitem_ids],
        prevent_initial_call=False
    )
    def update_active_subitem_and_view(*args):
        ctx = callback_context
        if not ctx.triggered:
            # Par défaut : "Pods" actif et vue des pods affichée
            return ["sidebar-subitem active" if id == "workloads-pods" else "sidebar-subitem" for id in all_subitem_ids] + [{'display': 'block'}, {'display': 'none'}, "Pods"]
        else:
            triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
            if triggered_id == "workloads-pods":
                return ["sidebar-subitem active" if id == "workloads-pods" else "sidebar-subitem" for id in all_subitem_ids] + [{'display': 'block'}, {'display': 'none'}, "Pods"]
            elif triggered_id == "workloads-deployments":
                return ["sidebar-subitem active" if id == "workloads-deployments" else "sidebar-subitem" for id in all_subitem_ids] + [{'display': 'none'}, {'display': 'block'}, "Deployments"]
            else:
                # Pour les autres sous-menus, garder la vue des pods par défaut
                return ["sidebar-subitem active" if id == triggered_id else "sidebar-subitem" for id in all_subitem_ids] + [{'display': 'block'}, {'display': 'none'}, "Pods"]

    # Callback pour afficher un message dans la console
    @app.callback(
        Output('dummy-output', 'children'),
        Input('connect-button', 'n_clicks'),
        prevent_initial_call=False
    )
    def log_connection_attempt(n_clicks):
        if n_clicks:
            print(f"Bouton de connexion cliqué! (clic #{n_clicks})")
        return None

    # Mise à jour des données des pods
    @app.callback(
        [Output('pods-data-store', 'data'),
         Output('connection-status', 'children')],
        [Input('connect-button', 'n_clicks'),
         Input('refresh-button', 'n_clicks'),
         Input('namespace-dropdown', 'value')],
        prevent_initial_call=True
    )
    def update_pods_data(connect_clicks, refresh_clicks, namespace):
        return get_pods(namespace)

    # Filtrage des pods dans le tableau
    @app.callback(
        Output('pods-table', 'data'),
        [Input('search-input', 'value'),
         Input('pods-data-store', 'data')]
    )
    def filter_pods(search_term, pods_data):
        if pods_data is None:
            return []
        if search_term:
            return [pod for pod in pods_data if search_term.lower() in pod['name'].lower()]
        return pods_data

    # Affichage des détails d'un pod sélectionné
    @app.callback(
        Output('pod-details', 'children'),
        Input('pods-table', 'selected_rows'),
        State('pods-table', 'data')
    )
    def update_pod_details(selected_rows, data):
        if selected_rows:
            pod = data[selected_rows[0]]
            return get_pod_details(pod['name'], pod['namespace'])
        return "Sélectionnez un pod pour voir les détails"

    # Mise à jour des données des déploiements avec allow_duplicate=True
    @app.callback(
        [Output('deployments-data-store', 'data', allow_duplicate=True),
         Output('connection-status', 'children', allow_duplicate=True)],
        [Input('connect-button', 'n_clicks'),
         Input('refresh-button', 'n_clicks'),
         Input('namespace-dropdown', 'value')],
        prevent_initial_call=True
    )
    def update_deployments_data(connect_clicks, refresh_clicks, namespace):
        return get_deployments(namespace)

    # Filtrage des déploiements dans le tableau
    @app.callback(
        Output('deployments-table', 'data'),
        [Input('search-input', 'value'),
         Input('deployments-data-store', 'data')]
    )
    def filter_deployments(search_term, deployments_data):
        if deployments_data is None:
            return []
        if search_term:
            return [deployment for deployment in deployments_data if search_term.lower() in deployment['name'].lower()]
        return deployments_data

    # Affichage des détails d'un déploiement sélectionné
    @app.callback(
        Output('deployment-details', 'children'),
        Input('deployments-table', 'selected_rows'),
        State('deployments-table', 'data')
    )
    def update_deployment_details(selected_rows, data):
        if selected_rows:
            deployment = data[selected_rows[0]]
            return get_deployment_details(deployment['name'], deployment['namespace'])
        return "Sélectionnez un déploiement pour voir les détails"

    # Afficher/masquer les sous-menus Workloads
    @app.callback(
        [Output('workloads-subitems', 'style'),
         Output('workloads-menu-state', 'data')],
        Input('workloads-nav', 'n_clicks'),
        State('workloads-menu-state', 'data'),
        prevent_initial_call=True
    )
    def toggle_workloads_menu(n_clicks, state):
        if n_clicks is None:
            return {'display': 'none'}, state
        open_state = not state['open']
        return {'display': 'block' if open_state else 'none'}, {'open': open_state}

    # Afficher/masquer les sous-menus Config
    @app.callback(
        [Output('config-subitems', 'style'),
         Output('config-menu-state', 'data')],
        Input('config-nav', 'n_clicks'),
        State('config-menu-state', 'data'),
        prevent_initial_call=True
    )
    def toggle_config_menu(n_clicks, state):
        if n_clicks is None:
            return {'display': 'none'}, state
        open_state = not state['open']
        return {'display': 'block' if open_state else 'none'}, {'open': open_state}

    # Afficher/masquer les sous-menus Network
    @app.callback(
        [Output('network-subitems', 'style'),
         Output('network-menu-state', 'data')],
        Input('network-nav', 'n_clicks'),
        State('network-menu-state', 'data'),
        prevent_initial_call=True
    )
    def toggle_network_menu(n_clicks, state):
        if n_clicks is None:
            return {'display': 'none'}, state
        open_state = not state['open']
        return {'display': 'block' if open_state else 'none'}, {'open': open_state}

    # Afficher/masquer les sous-menus Storage
    @app.callback(
        [Output('storage-subitems', 'style'),
         Output('storage-menu-state', 'data')],
        Input('storage-nav', 'n_clicks'),
        State('storage-menu-state', 'data'),
        prevent_initial_call=True
    )
    def toggle_storage_menu(n_clicks, state):
        if n_clicks is None:
            return {'display': 'none'}, state
        open_state = not state['open']
        return {'display': 'block' if open_state else 'none'}, {'open': open_state}