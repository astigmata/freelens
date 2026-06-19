"""Operations on Kubernetes objects: YAML rendering, logs and write actions.

Kept separate from the read-only listing logic in ``registry`` so that the
mutating calls (scale / restart / delete) live in one auditable place.
"""

import datetime

import yaml
from kubernetes import client as k8s

from .client import Clients


# Secret kinds whose value maps must never be rendered. The base64 in a Secret's
# ``data`` is only an encoding, not encryption, so dumping it leaks the value.
_SECRET_VALUE_KEYS = ("data", "stringData")


def _redact_secret(data: dict) -> dict:
    """Replace Secret value maps with a placeholder, keeping the key names.

    The detail panel already shows only key names on purpose; this keeps the YAML
    tab consistent and avoids leaking credentials (and possibly PHI) in clear.
    """
    if not isinstance(data, dict) or data.get("kind") != "Secret":
        return data
    for key in _SECRET_VALUE_KEYS:
        values = data.get(key)
        if isinstance(values, dict):
            data[key] = {name: "<redacted>" for name in values}
    return data


def to_yaml(obj) -> str:
    """Serialize a Kubernetes API object to a clean YAML manifest.

    Secret values are redacted: their base64 ``data`` is an encoding, not a
    protection, so it is never rendered.
    """
    data = k8s.ApiClient().sanitize_for_serialization(obj)
    # The typed read API does not always populate kind/apiVersion; set it from
    # the Python type so the redaction below can recognise a Secret.
    if isinstance(obj, k8s.V1Secret):
        data["kind"] = "Secret"
    data = _redact_secret(data)
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


def list_containers(clients: Clients, name: str, namespace: str) -> list[str]:
    pod = clients.core.read_namespaced_pod(name, namespace)
    return [c.name for c in pod.spec.containers]


def pod_logs(
    clients: Clients,
    name: str,
    namespace: str,
    container: str | None = None,
    tail_lines: int = 500,
) -> str:
    return clients.core.read_namespaced_pod_log(
        name,
        namespace,
        container=container,
        tail_lines=tail_lines,
        timestamps=True,
    )


# --------------------------------------------------------------------------- #
# Write actions.
# --------------------------------------------------------------------------- #
def scale_deployment(clients: Clients, name: str, namespace: str, replicas: int) -> None:
    clients.apps.patch_namespaced_deployment_scale(
        name, namespace, {"spec": {"replicas": int(replicas)}}
    )


def restart_deployment(clients: Clients, name: str, namespace: str) -> None:
    """Trigger a rolling restart, the way ``kubectl rollout restart`` does."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    patch = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {"kubectl.kubernetes.io/restartedAt": now}
                }
            }
        }
    }
    clients.apps.patch_namespaced_deployment(name, namespace, patch)


def delete_pod(clients: Clients, name: str, namespace: str) -> None:
    clients.core.delete_namespaced_pod(name, namespace)
