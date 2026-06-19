"""Custom Resource Definitions and their instances, discovered at runtime.

CRDs vary per cluster and can appear or disappear while the app runs (installing
metallb adds the ``metallb.io`` CRDs, for instance), so they don't fit the
static ``ResourceDescriptor`` registry. Instead we discover them live via the
apiextensions API and read their instances through the dynamic
``CustomObjectsApi`` — which returns plain dicts rather than typed objects.
"""

import datetime
import logging

from . import formatters as fmt
from .client import Clients

log = logging.getLogger(__name__)


def _storage_version(spec) -> str | None:
    """The version marked for storage, falling back to the first served one."""
    for v in spec.versions or []:
        if v.storage:
            return v.name
    return spec.versions[0].name if spec.versions else None


def list_crds(clients: Clients) -> list[dict]:
    """Return a sorted, lightweight description of every CRD in the cluster."""
    items = clients.apiext.list_custom_resource_definition().items
    crds = []
    for crd in items:
        spec = crd.spec
        version = _storage_version(spec)
        if not version:
            continue
        crds.append(
            {
                "group": spec.group,
                "version": version,
                "plural": spec.names.plural,
                "kind": spec.names.kind,
                "namespaced": spec.scope == "Namespaced",
            }
        )
    return sorted(crds, key=lambda c: (c["group"], c["kind"]))


def list_instances(
    clients: Clients,
    group: str,
    version: str,
    plural: str,
    namespaced: bool,
    namespace: str = "all",
) -> list[dict]:
    api = clients.custom
    if namespaced and namespace and namespace != "all":
        resp = api.list_namespaced_custom_object(group, version, namespace, plural)
    else:
        # Works for cluster-scoped CRDs and for namespaced ones across all namespaces.
        resp = api.list_cluster_custom_object(group, version, plural)
    return resp.get("items", [])


def get_instance(
    clients: Clients,
    group: str,
    version: str,
    plural: str,
    namespaced: bool,
    namespace: str,
    name: str,
) -> dict:
    api = clients.custom
    if namespaced:
        return api.get_namespaced_custom_object(group, version, namespace, plural, name)
    return api.get_cluster_custom_object(group, version, plural, name)


def _age(timestamp: str | None) -> str:
    if not timestamp:
        return "N/A"
    try:
        dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    return fmt.age_short(dt)


def to_rows(items: list[dict]) -> list[dict]:
    """Flatten CR instances into table rows (name / namespace / age)."""
    rows = []
    for item in items:
        meta = item.get("metadata", {})
        rows.append(
            {
                "name": meta.get("name", ""),
                "namespace": meta.get("namespace", ""),
                "age": _age(meta.get("creationTimestamp")),
            }
        )
    return rows
