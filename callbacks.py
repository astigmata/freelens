from dash.dependencies import Input, Output, State
from kubernetes_api import get_pods, get_pod_details

def register_callbacks(app):
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
        return get_pods(namespace)

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
            return get_pod_details(pod['name'], pod['namespace'])
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
