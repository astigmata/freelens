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
        pod = api.read_namespaced_pod(name, namespace)
        creation_time = pod.metadata.creation_timestamp
        age = datetime.datetime.now(creation_time.tzinfo) - creation_time
        age_str = f"{age.days}d {age.seconds//3600}h {age.seconds//60 % 60}m ago"
        created = creation_time.strftime("%Y-%m-%dT%H:%M:%S%z")
        labels = [html.Li(f"{key}: {value}") for key, value in pod.metadata.labels.items()] if pod.metadata.labels else [html.Li("N/A")]
        annotations = [html.Li(f"{key}: {value}") for key, value in pod.metadata.annotations.items()] if pod.metadata.annotations else [html.Li("N/A")]
        controlled_by = f"{pod.metadata.owner_references[0].kind}/{pod.metadata.owner_references[0].name}" if pod.metadata.owner_references else "N/A"
        status_class = {"Running": "status-running", "Pending": "status-pending", "Failed": "status-failed"}.get(pod.status.phase, "")
        pod_ip = pod.status.pod_ip if pod.status.pod_ip else "N/A"
        service_account = pod.spec.service_account_name if pod.spec.service_account_name else "N/A"
        priority_class = pod.spec.priority_class_name if pod.spec.priority_class_name else "N/A"
        qos_class = pod.status.qos_class if pod.status.qos_class else "N/A"
        conditions = [html.Li(f"{condition.type}: {condition.status}") for condition in pod.status.conditions] if pod.status.conditions else [html.Li("N/A")]
        return html.Div([
            html.H3(f"Pod: {name}"),
            html.Div([html.Span("Created: ", className="detail-label"), html.Span(f"{age_str} {created}", className="detail-value")], className="detail-row"),
            html.Div([html.Span("Name: ", className="detail-label"), html.Span(name, className="detail-value")], className="detail-row"),
            html.Div([html.Span("Namespace: ", className="detail-label"), html.Span(namespace, className="detail-value")], className="detail-row"),
            html.Div([html.Span("Labels: ", className="detail-label"), html.Ul(labels, className="detail-list")], className="detail-row"),
            html.Div([html.Span("Annotations: ", className="detail-label"), html.Ul(annotations, className="detail-list")], className="detail-row"),
            html.Div([html.Span("Controlled By: ", className="detail-label"), html.Span(controlled_by, className="detail-value")], className="detail-row"),
            html.Div([html.Span("Status: ", className="detail-label"), html.Span(pod.status.phase, className=f"detail-value {status_class}")], className="detail-row"),
            html.Div([html.Span("Node: ", className="detail-label"), html.Span(pod.spec.node_name if pod.spec.node_name else "N/A", className="detail-value")], className="detail-row"),
            html.Div([html.Span("Pod IP: ", className="detail-label"), html.Span(pod_ip, className="detail-value")], className="detail-row"),
            html.Div([html.Span("Service Account: ", className="detail-label"), html.Span(service_account, className="detail-value")], className="detail-row"),
            html.Div([html.Span("Priority Class: ", className="detail-label"), html.Span(priority_class, className="detail-value")], className="detail-row"),
            html.Div([html.Span("QoS Class: ", className="detail-label"), html.Span(qos_class, className="detail-value")], className="detail-row"),
            html.Div([html.Span("Conditions: ", className="detail-label"), html.Ul(conditions, className="detail-list")], className="detail-row"),
        ])
    except Exception as e:
        return html.Div(f"Erreur lors de la récupération des détails du pod: {str(e)}")

def get_deployments(namespace):
    try:
        config.load_kube_config()
        api = client.AppsV1Api()
        if namespace == 'all':
            deployments = api.list_deployment_for_all_namespaces(watch=False)
        else:
            deployments = api.list_namespaced_deployment(namespace, watch=False)
        deployments_data = []
        for deployment in deployments.items:
            creation_time = deployment.metadata.creation_timestamp
            age = datetime.datetime.now(creation_time.tzinfo) - creation_time
            age_str = f"{age.days}d" if age.days > 0 else f"{int(age.seconds / 3600)}h"
            deployments_data.append({
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "replicas": f"{deployment.status.ready_replicas or 0}/{deployment.spec.replicas}",
                "up_to_date": deployment.status.updated_replicas or 0,
                "available": deployment.status.available_replicas or 0,
                "age": age_str,
                "strategy": deployment.spec.strategy.type,
                "labels": ", ".join([f"{k}={v}" for k, v in deployment.metadata.labels.items()]) if deployment.metadata.labels else "N/A"
            })
        return deployments_data, "Connecté"
    except Exception as e:
        return [], f"Erreur: {str(e)}"

def get_deployment_details(name, namespace):
    try:
        config.load_kube_config()
        api = client.AppsV1Api()
        deployment = api.read_namespaced_deployment(name, namespace)
        creation_time = deployment.metadata.creation_timestamp
        age = datetime.datetime.now(creation_time.tzinfo) - creation_time
        age_str = f"{age.days}d {age.seconds//3600}h {age.seconds//60 % 60}m ago"
        created = creation_time.strftime("%Y-%m-%dT%H:%M:%S%z")
        labels = [html.Li(f"{key}: {value}") for key, value in deployment.metadata.labels.items()] if deployment.metadata.labels else [html.Li("N/A")]
        annotations = [html.Li(f"{key}: {value}") for key, value in deployment.metadata.annotations.items()] if deployment.metadata.annotations else [html.Li("N/A")]
        selector = [html.Li(f"{key}: {value}") for key, value in deployment.spec.selector.match_labels.items()] if deployment.spec.selector.match_labels else [html.Li("N/A")]
        return html.Div([
            html.H3(f"Deployment: {name}"),
            html.Div([html.Span("Created: ", className="detail-label"), html.Span(f"{age_str} {created}", className="detail-value")], className="detail-row"),
            html.Div([html.Span("Name: ", className="detail-label"), html.Span(name, className="detail-value")], className="detail-row"),
            html.Div([html.Span("Namespace: ", className="detail-label"), html.Span(namespace, className="detail-value")], className="detail-row"),
            html.Div([html.Span("Labels: ", className="detail-label"), html.Ul(labels, className="detail-list")], className="detail-row"),
            html.Div([html.Span("Annotations: ", className="detail-label"), html.Ul(annotations, className="detail-list")], className="detail-row"),
            html.Div([html.Span("Selector: ", className="detail-label"), html.Ul(selector, className="detail-list")], className="detail-row"),
            html.Div([html.Span("Replicas: ", className="detail-label"), html.Span(f"{deployment.status.ready_replicas or 0}/{deployment.spec.replicas}", className="detail-value")], className="detail-row"),
            html.Div([html.Span("Strategy: ", className="detail-label"), html.Span(deployment.spec.strategy.type, className="detail-value")], className="detail-row"),
            html.Div([html.Span("Min Ready Seconds: ", className="detail-label"), html.Span(str(deployment.spec.min_ready_seconds or 0), className="detail-value")], className="detail-row"),
            html.Div([html.Span("Revision History Limit: ", className="detail-label"), html.Span(str(deployment.spec.revision_history_limit or "N/A"), className="detail-value")], className="detail-row"),
            html.Div([html.Span("Progress Deadline Seconds: ", className="detail-label"), html.Span(str(deployment.spec.progress_deadline_seconds or "N/A"), className="detail-value")], className="detail-row"),
        ])
    except Exception as e:
        return html.Div(f"Erreur lors de la récupération des détails du déploiement: {str(e)}")