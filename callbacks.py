from dash import Input, Output, State, callback_context
from dash import html
from kubernetes_api import get_pods, get_pod_details, get_deployments, get_deployment_details, get_daemon_sets


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
         Output('daemon-set-view', 'style'),
         Output('page-title', 'children')],
        [Input(id, 'n_clicks') for id in all_subitem_ids],
        prevent_initial_call=False
    )
    def update_active_subitem_and_view(*args):
        ctx = callback_context
        if not ctx.triggered:
            # Par défaut : "Pods" actif et vue des pods affichée
            return (["sidebar-subitem active" if id == "workloads-pods" else "sidebar-subitem" for id in
                     all_subitem_ids] +
                    [{'display': 'block'}, {'display': 'none'}, {'display': 'none'}, "Pods"])
        else:
            triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

            if triggered_id == "workloads-pods":
                return (["sidebar-subitem active" if id == "workloads-pods" else "sidebar-subitem" for id in
                         all_subitem_ids] +
                        [{'display': 'block'}, {'display': 'none'}, {'display': 'none'}, "Pods"])
            elif triggered_id == "workloads-deployments":
                return (["sidebar-subitem active" if id == "workloads-deployments" else "sidebar-subitem" for id in
                         all_subitem_ids] +
                        [{'display': 'none'}, {'display': 'block'}, {'display': 'none'}, "Deployments"])
            elif triggered_id == "workloads-daemonsets":
                return (["sidebar-subitem active" if id == "workloads-daemonsets" else "sidebar-subitem" for id in
                         all_subitem_ids] +
                        [{'display': 'none'}, {'display': 'none'}, {'display': 'block'}, "DaemonSets"])
            else:
                # Pour les autres sous-menus, garder la vue des pods par défaut
                return (["sidebar-subitem active" if id == triggered_id else "sidebar-subitem" for id in
                         all_subitem_ids] +
                        [{'display': 'block'}, {'display': 'none'}, {'display': 'none'}, "Pods"])

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

    # Mise à jour des données des ressources (pods, deployments, daemonsets) en fonction du bouton cliqué
    @app.callback(
        [Output('pods-data-store', 'data'),
         Output('deployments-data-store', 'data'),
         Output('daemon-sets-data-store', 'data'),
         Output('pods-connection-status', 'children'),
         Output('deployments-connection-status', 'children'),
         Output('daemon-sets-connection-status', 'children')],
        [Input('connect-button', 'n_clicks'),
         Input('refresh-button', 'n_clicks'),
         Input('namespace-dropdown', 'value')],
        prevent_initial_call=True
    )
    def update_resources_data(connect_clicks, refresh_clicks, namespace):
        ctx = callback_context
        triggered = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

        # Initialisation des valeurs par défaut
        pods_data, pods_status = [], "Non connecté"
        deployments_data, deployments_status = [], "Non connecté"
        daemon_sets_data, daemon_sets_status = [], "Non connecté"

        # Si un bouton a été cliqué ou le namespace a changé, mettre à jour toutes les données
        if triggered:
            pods_data, pods_status = get_pods(namespace)
            deployments_data, deployments_status = get_deployments(namespace)
            daemon_sets_data, daemon_sets_status = get_daemon_sets(namespace)

        return pods_data, deployments_data, daemon_sets_data, pods_status, deployments_status, daemon_sets_status

    # Filtrage des pods dans le tableau
    @app.callback(
        Output('pods-table', 'data'),
        [Input('pods-search-input', 'value'),
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
        if selected_rows and data:
            pod = data[selected_rows[0]]
            return get_pod_details(pod['name'], pod['namespace'])
        return "Sélectionnez un pod pour voir les détails"

    # Filtrage des déploiements dans le tableau
    @app.callback(
        Output('deployments-table', 'data'),
        [Input('deployments-search-input', 'value'),
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
        if selected_rows and data:
            deployment = data[selected_rows[0]]
            return get_deployment_details(deployment['name'], deployment['namespace'])
        return "Sélectionnez un déploiement pour voir les détails"

    # Filtrage des daemon sets dans le tableau
    @app.callback(
        Output('daemon-sets-table', 'data'),
        [Input('daemon-sets-search-input', 'value'),
         Input('daemon-sets-data-store', 'data')]
    )
    def filter_daemon_sets(search_term, daemon_sets_data):
        if daemon_sets_data is None:
            return []
        if search_term:
            return [ds for ds in daemon_sets_data if search_term.lower() in ds['name'].lower()]
        return daemon_sets_data

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
