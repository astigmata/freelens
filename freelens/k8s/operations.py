"""Operations on Kubernetes objects: YAML rendering, logs and write actions.

Kept separate from the read-only listing logic in ``registry`` so that the
mutating calls (scale / restart / delete) live in one auditable place.
"""

import datetime

import yaml
from kubernetes import client as k8s
from kubernetes.stream import stream

from .client import Clients


def to_yaml(obj) -> str:
    """Serialize a Kubernetes API object to a clean YAML manifest."""
    data = k8s.ApiClient().sanitize_for_serialization(obj)
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


def exec_command(
    clients: Clients,
    name: str,
    namespace: str,
    container: str | None,
    command: str,
) -> str:
    """Run a shell command in a pod container and return combined stdout/stderr.

    Non-interactive (no TTY): the command runs through ``/bin/sh -c`` and its
    output is captured in one shot — the equivalent of ``kubectl exec``, not an
    interactive shell session.
    """
    return stream(
        clients.core.connect_get_namespaced_pod_exec,
        name,
        namespace,
        container=container,
        command=["/bin/sh", "-c", command],
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
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
