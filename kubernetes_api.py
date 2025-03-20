from kubernetes import client, config
import datetime
from dash import html

def get_pods(namespace):
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

def get_pod_details(name, namespace):
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
        controlled_by = f"{pod_details.metadata.owner_references[0].kind}/{pod_details.metadata.owner_references[0].name}" if pod_details.metadata.owner_references else "N/A"

        # Status avec classe CSS pour la couleur
        status_class = {
            "Running": "status-running",
            "Pending": "status-pending",
            "Failed": "status-failed"
        }.get(pod_details.status.phase, "")

        # Pod IP
        pod_ip = pod_details.status.pod_ip if pod_details.status.pod_ip else "N/A"

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
                html.Span(pod_details.spec.node_name if pod_details.spec.node_name else "N/A",
                          className="detail-value"),
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
        ])

    except Exception as e:
        return html.Div(f"Erreur lors de la récupération des détails du pod: {str(e)}")
    else:
        return "Sélectionnez un pod pour voir les détails"
