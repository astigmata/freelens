"""Cached access to the Kubernetes API clients.

The kube config is loaded once (lazily), supporting both a local kubeconfig and
in-cluster service-account credentials, instead of being reloaded on every call.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Clients:
    """Bundle of the Kubernetes API clients used across the app."""

    core: client.CoreV1Api
    apps: client.AppsV1Api
    batch: client.BatchV1Api
    apiext: client.ApiextensionsV1Api  # CustomResourceDefinition discovery
    custom: client.CustomObjectsApi  # dynamic access to CRD instances


@lru_cache(maxsize=1)
def _load_config() -> None:
    """Load kube config once, preferring in-cluster credentials when present."""
    try:
        config.load_incluster_config()
        log.info("Loaded in-cluster Kubernetes config")
    except ConfigException:
        config.load_kube_config()
        log.info("Loaded local kubeconfig")


def _clients_from_api(api: client.ApiClient) -> Clients:
    return Clients(
        core=client.CoreV1Api(api),
        apps=client.AppsV1Api(api),
        batch=client.BatchV1Api(api),
        apiext=client.ApiextensionsV1Api(api),
        custom=client.CustomObjectsApi(api),
    )


@lru_cache(maxsize=1)
def get_clients() -> Clients:
    """Return cached Kubernetes API clients for the app's own identity."""
    _load_config()
    return _clients_from_api(client.ApiClient())


@lru_cache(maxsize=64)
def get_user_clients(user: str, groups: tuple[str, ...] = ()) -> Clients:
    """Return clients that impersonate ``user`` (and ``groups``) at the API server.

    The API server then enforces that user's RBAC and records the real actor in
    its audit log, giving end-to-end imputability. The app's ServiceAccount must
    hold the ``impersonate`` verb on users (and groups). Cached per identity so
    repeated calls in a session don't rebuild the client.
    """
    _load_config()
    cfg = client.Configuration.get_default_copy()
    api = client.ApiClient(cfg)
    api.set_default_header("Impersonate-User", user)
    # The kubernetes client maps a list value to repeated headers, which is how
    # multiple Impersonate-Group values are sent.
    if groups:
        api.set_default_header("Impersonate-Group", list(groups))
    return _clients_from_api(api)


def get_namespaces(clients: "Clients | None" = None) -> list[str]:
    """List all namespace names in the cluster."""
    clients = clients or get_clients()
    return [ns.metadata.name for ns in clients.core.list_namespace().items]


def current_context() -> str | None:
    """Name of the active kube context, or None when unavailable."""
    try:
        _, active = config.list_kube_config_contexts()
        return active["name"] if active else None
    except Exception:  # noqa: BLE001 — in-cluster or missing kubeconfig
        return None
