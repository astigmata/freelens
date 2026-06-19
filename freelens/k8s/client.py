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


@lru_cache(maxsize=1)
def _load_config() -> None:
    """Load kube config once, preferring in-cluster credentials when present."""
    try:
        config.load_incluster_config()
        log.info("Loaded in-cluster Kubernetes config")
    except ConfigException:
        config.load_kube_config()
        log.info("Loaded local kubeconfig")


@lru_cache(maxsize=1)
def get_clients() -> Clients:
    """Return cached Kubernetes API clients."""
    _load_config()
    return Clients(
        core=client.CoreV1Api(),
        apps=client.AppsV1Api(),
        batch=client.BatchV1Api(),
    )


def get_namespaces() -> list[str]:
    """List all namespace names in the cluster."""
    clients = get_clients()
    return [ns.metadata.name for ns in clients.core.list_namespace().items]


def current_context() -> str | None:
    """Name of the active kube context, or None when unavailable."""
    try:
        _, active = config.list_kube_config_contexts()
        return active["name"] if active else None
    except Exception:  # noqa: BLE001 — in-cluster or missing kubeconfig
        return None
