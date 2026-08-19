"""Declarative description of every Kubernetes resource the UI can show.

This registry is the single source of truth. Adding a new resource type means
adding one ``ResourceDescriptor`` here — the sidebar, routing, table, detail
panel, YAML/logs tabs and write actions are all generated from it. No layout or
callback code needs to change.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import formatters as fmt
from . import operations as ops
from .client import Clients, get_clients

log = logging.getLogger(__name__)


def _slug(label: str) -> str:
    return label.lower().replace(" ", "_").replace("-", "_")


@dataclass(frozen=True)
class Column:
    """A table column: a header label and an accessor on a raw API object."""

    label: str
    accessor: Callable[[Any], Any]

    @property
    def id(self) -> str:
        return _slug(self.label)


@dataclass(frozen=True)
class DetailField:
    """A row in the detail panel. ``kind`` drives how it is rendered."""

    label: str
    accessor: Callable[[Any], Any]
    kind: str = "text"  # "text" | "list" | "status"


@dataclass(frozen=True)
class ResourceAction:
    """A write action exposed as a button on the detail panel."""

    key: str
    label: str
    fn: Callable[[Clients, str, str, Any], None]
    needs_value: bool = False
    value_label: str = ""
    value_default: Any = ""
    destructive: bool = False


@dataclass(frozen=True)
class ResourceDescriptor:
    key: str
    label: str
    columns: list[Column]
    detail_fields: list[DetailField]
    list_fn: Callable[[Clients, str], list]
    get_fn: Callable[[Clients, str, str], Any]
    namespaced: bool = True
    supports_logs: bool = False
    supports_exec: bool = False
    supports_forward: bool = False
    actions: tuple[ResourceAction, ...] = ()
    table_conditional: list = field(default_factory=list)
    # Generic delete used by bulk selection; None => not bulk-deletable.
    delete_fn: Callable[[Clients, str, str], None] | None = None

    @property
    def title(self) -> str:
        return self.label

    def table_columns(self) -> list[dict]:
        return [{"name": c.label, "id": c.id} for c in self.columns]

    def action(self, key: str) -> ResourceAction | None:
        return next((a for a in self.actions if a.key == key), None)


# --------------------------------------------------------------------------- #
# Generic data access (replaces the per-resource get_* functions).
# --------------------------------------------------------------------------- #
def list_rows(
    descriptor: ResourceDescriptor, namespace: str, clients: Clients | None = None
) -> tuple[list[dict], str]:
    """Return table rows for a resource, plus a connection-status message."""
    try:
        clients = clients or get_clients()
        objs = descriptor.list_fn(clients, namespace)
        rows = [
            {col.id: str(col.accessor(obj)) for col in descriptor.columns}
            for obj in objs
        ]
        for row in rows:
            # Stable, unique row id so row selection survives sorting, filtering
            # and pagination (Dash tracks selection by id, not by index).
            row["id"] = f"{row.get('namespace', '')}/{row['name']}"
        return rows, "Connected"
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not list %s: %s", descriptor.key, exc)
        return [], "Error"


def get_object(
    descriptor: ResourceDescriptor, name: str, namespace: str, clients: Clients | None = None
) -> Any:
    return descriptor.get_fn(clients or get_clients(), name, namespace or "")


# --------------------------------------------------------------------------- #
# Accessor + descriptor-building helpers, to keep descriptors declarative.
# --------------------------------------------------------------------------- #
_NAME = lambda o: o.metadata.name  # noqa: E731
_NS = lambda o: o.metadata.namespace  # noqa: E731
_AGE = lambda o: fmt.age_short(o.metadata.creation_timestamp)  # noqa: E731


def _ns_list(api_attr: str, all_fn: str, ns_fn: str):
    """Build a list_fn for a namespaced resource (honours 'all' namespaces)."""

    def fn(clients: Clients, namespace: str):
        api = getattr(clients, api_attr)
        if namespace == "all":
            return getattr(api, all_fn)(watch=False).items
        return getattr(api, ns_fn)(namespace, watch=False).items

    return fn


def _cluster_list(api_attr: str, fn_name: str):
    """Build a list_fn for a cluster-scoped (non-namespaced) resource."""
    return lambda clients, _ns: getattr(getattr(clients, api_attr), fn_name)(
        watch=False
    ).items


def _get(api_attr: str, fn_name: str, namespaced: bool = True):
    if namespaced:
        return lambda c, name, ns: getattr(getattr(c, api_attr), fn_name)(name, ns)
    return lambda c, name, _ns: getattr(getattr(c, api_attr), fn_name)(name)


def _delete(api_attr: str, fn_name: str, namespaced: bool = True):
    if namespaced:
        return lambda c, name, ns: getattr(getattr(c, api_attr), fn_name)(name, ns)
    return lambda c, name, _ns: getattr(getattr(c, api_attr), fn_name)(name)


def _common_details(namespaced: bool = True) -> list[DetailField]:
    fields = [
        DetailField(
            "Created",
            lambda o: f"{fmt.age_long(o.metadata.creation_timestamp)} "
            f"{fmt.created_at(o.metadata.creation_timestamp)}",
        ),
        DetailField("Name", _NAME),
    ]
    if namespaced:
        fields.append(DetailField("Namespace", _NS))
    fields += [
        DetailField("Labels", lambda o: fmt.key_value_pairs(o.metadata.labels), "list"),
        DetailField(
            "Annotations", lambda o: fmt.key_value_pairs(o.metadata.annotations), "list"
        ),
    ]
    return fields


def _containers(pod) -> str:
    statuses = pod.status.container_statuses or []
    ready = sum(1 for c in statuses if c.ready)
    return f"{ready}/{len(pod.spec.containers)}"


def _restarts(pod) -> int:
    statuses = pod.status.container_statuses or []
    return sum(c.restart_count for c in statuses)


def _conditions(obj) -> list[str]:
    conditions = obj.status.conditions
    if not conditions:
        return ["N/A"]
    return [f"{c.type}: {c.status}" for c in conditions]


def _node_status(node) -> str:
    for cond in node.status.conditions or []:
        if cond.type == "Ready":
            return "Ready" if cond.status == "True" else "NotReady"
    return "Unknown"


def _node_roles(node) -> str:
    prefix = "node-role.kubernetes.io/"
    roles = [
        k[len(prefix):] or "master"
        for k in (node.metadata.labels or {})
        if k.startswith(prefix)
    ]
    return ", ".join(sorted(roles)) or "<none>"


def _ports(svc) -> str:
    return ", ".join(f"{p.port}/{p.protocol}" for p in (svc.spec.ports or [])) or "N/A"


# --------------------------------------------------------------------------- #
# Write actions.
# --------------------------------------------------------------------------- #
_SCALE = ResourceAction(
    "scale",
    "Scale",
    lambda c, n, ns, v: ops.scale_deployment(c, n, ns, v),
    needs_value=True,
    value_label="Replicas",
    value_default=1,
)
_RESTART = ResourceAction(
    "restart", "Restart", lambda c, n, ns, v: ops.restart_deployment(c, n, ns)
)
_DELETE_POD = ResourceAction(
    "delete",
    "Delete",
    lambda c, n, ns, v: ops.delete_pod(c, n, ns),
    destructive=True,
)


# --------------------------------------------------------------------------- #
# Resource descriptors.
# --------------------------------------------------------------------------- #
PODS = ResourceDescriptor(
    key="pods",
    label="Pods",
    list_fn=_ns_list("core", "list_pod_for_all_namespaces", "list_namespaced_pod"),
    get_fn=_get("core", "read_namespaced_pod"),
    delete_fn=_delete("core", "delete_namespaced_pod"),
    supports_logs=True,
    supports_exec=True,
    supports_forward=True,
    actions=(_DELETE_POD,),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Containers", _containers),
        Column("Restarts", _restarts),
        Column("Controlled By", lambda p: fmt.owner_ref(p.metadata)),
        Column("Node", lambda p: p.spec.node_name or "N/A"),
        Column("QoS", lambda p: p.status.qos_class or "N/A"),
        Column("Age", _AGE),
        Column("Status", lambda p: p.status.phase),
    ],
    table_conditional=[
        {"if": {"filter_query": '{status} = "Running"'}, "color": "var(--success)"},
        {"if": {"filter_query": '{status} = "Pending"'}, "color": "var(--warning)"},
        {"if": {"filter_query": '{status} = "Failed"'}, "color": "var(--danger)"},
    ],
    detail_fields=[
        DetailField(
            "Created",
            lambda p: f"{fmt.age_long(p.metadata.creation_timestamp)} "
            f"{fmt.created_at(p.metadata.creation_timestamp)}",
        ),
        DetailField("Name", _NAME),
        DetailField("Namespace", _NS),
        DetailField("Labels", lambda p: fmt.key_value_pairs(p.metadata.labels), "list"),
        DetailField(
            "Annotations", lambda p: fmt.key_value_pairs(p.metadata.annotations), "list"
        ),
        DetailField("Controlled By", lambda p: fmt.owner_ref(p.metadata)),
        DetailField("Status", lambda p: p.status.phase, "status"),
        DetailField("Node", lambda p: p.spec.node_name or "N/A"),
        DetailField("Pod IP", lambda p: p.status.pod_ip or "N/A"),
        DetailField("Service Account", lambda p: p.spec.service_account_name or "N/A"),
        DetailField("Priority Class", lambda p: p.spec.priority_class_name or "N/A"),
        DetailField("QoS Class", lambda p: p.status.qos_class or "N/A"),
        DetailField("Conditions", _conditions, "list"),
    ],
)


DEPLOYMENTS = ResourceDescriptor(
    key="deployments",
    label="Deployments",
    list_fn=_ns_list(
        "apps", "list_deployment_for_all_namespaces", "list_namespaced_deployment"
    ),
    get_fn=_get("apps", "read_namespaced_deployment"),
    delete_fn=_delete("apps", "delete_namespaced_deployment"),
    actions=(_SCALE, _RESTART),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Replicas", lambda d: f"{d.status.ready_replicas or 0}/{d.spec.replicas}"),
        Column("Up-to-date", lambda d: d.status.updated_replicas or 0),
        Column("Available", lambda d: d.status.available_replicas or 0),
        Column("Age", _AGE),
        Column("Strategy", lambda d: d.spec.strategy.type),
        Column("Labels", lambda d: fmt.joined_labels(d.metadata.labels)),
    ],
    detail_fields=[
        DetailField(
            "Created",
            lambda d: f"{fmt.age_long(d.metadata.creation_timestamp)} "
            f"{fmt.created_at(d.metadata.creation_timestamp)}",
        ),
        DetailField("Name", _NAME),
        DetailField("Namespace", _NS),
        DetailField("Labels", lambda d: fmt.key_value_pairs(d.metadata.labels), "list"),
        DetailField(
            "Annotations", lambda d: fmt.key_value_pairs(d.metadata.annotations), "list"
        ),
        DetailField(
            "Selector", lambda d: fmt.key_value_pairs(d.spec.selector.match_labels), "list"
        ),
        DetailField(
            "Replicas", lambda d: f"{d.status.ready_replicas or 0}/{d.spec.replicas}"
        ),
        DetailField("Strategy", lambda d: d.spec.strategy.type),
        DetailField("Min Ready Seconds", lambda d: d.spec.min_ready_seconds or 0),
        DetailField(
            "Revision History Limit", lambda d: d.spec.revision_history_limit or "N/A"
        ),
        DetailField(
            "Progress Deadline Seconds",
            lambda d: d.spec.progress_deadline_seconds or "N/A",
        ),
    ],
)


DAEMONSETS = ResourceDescriptor(
    key="daemonsets",
    label="DaemonSets",
    list_fn=_ns_list(
        "apps", "list_daemon_set_for_all_namespaces", "list_namespaced_daemon_set"
    ),
    get_fn=_get("apps", "read_namespaced_daemon_set"),
    delete_fn=_delete("apps", "delete_namespaced_daemon_set"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Desired", lambda d: d.status.desired_number_scheduled),
        Column("Current", lambda d: d.status.current_number_scheduled),
        Column("Ready", lambda d: d.status.number_ready),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField("Desired", lambda d: d.status.desired_number_scheduled),
        DetailField("Ready", lambda d: d.status.number_ready),
        DetailField("Available", lambda d: d.status.number_available or 0),
    ],
)


STATEFULSETS = ResourceDescriptor(
    key="statefulsets",
    label="StatefulSets",
    list_fn=_ns_list(
        "apps", "list_stateful_set_for_all_namespaces", "list_namespaced_stateful_set"
    ),
    get_fn=_get("apps", "read_namespaced_stateful_set"),
    delete_fn=_delete("apps", "delete_namespaced_stateful_set"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Replicas", lambda s: f"{s.status.ready_replicas or 0}/{s.spec.replicas}"),
        Column("Service", lambda s: s.spec.service_name),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField(
            "Replicas", lambda s: f"{s.status.ready_replicas or 0}/{s.spec.replicas}"
        ),
        DetailField("Service Name", lambda s: s.spec.service_name),
    ],
)


REPLICASETS = ResourceDescriptor(
    key="replicasets",
    label="ReplicaSets",
    list_fn=_ns_list(
        "apps", "list_replica_set_for_all_namespaces", "list_namespaced_replica_set"
    ),
    get_fn=_get("apps", "read_namespaced_replica_set"),
    delete_fn=_delete("apps", "delete_namespaced_replica_set"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Desired", lambda r: r.spec.replicas),
        Column("Current", lambda r: r.status.replicas or 0),
        Column("Ready", lambda r: r.status.ready_replicas or 0),
        Column("Controlled By", lambda r: fmt.owner_ref(r.metadata)),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [DetailField("Controlled By", lambda r: fmt.owner_ref(r.metadata))],
)


JOBS = ResourceDescriptor(
    key="jobs",
    label="Jobs",
    list_fn=_ns_list("batch", "list_job_for_all_namespaces", "list_namespaced_job"),
    get_fn=_get("batch", "read_namespaced_job"),
    delete_fn=_delete("batch", "delete_namespaced_job"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Completions", lambda j: f"{j.status.succeeded or 0}/{j.spec.completions or 1}"),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField("Completions", lambda j: f"{j.status.succeeded or 0}/{j.spec.completions or 1}"),
        DetailField("Active", lambda j: j.status.active or 0),
        DetailField("Failed", lambda j: j.status.failed or 0),
    ],
)


CRONJOBS = ResourceDescriptor(
    key="cronjobs",
    label="CronJobs",
    list_fn=_ns_list(
        "batch", "list_cron_job_for_all_namespaces", "list_namespaced_cron_job"
    ),
    get_fn=_get("batch", "read_namespaced_cron_job"),
    delete_fn=_delete("batch", "delete_namespaced_cron_job"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Schedule", lambda c: c.spec.schedule),
        Column("Suspend", lambda c: bool(c.spec.suspend)),
        Column("Active", lambda c: len(c.status.active or [])),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField("Schedule", lambda c: c.spec.schedule),
        DetailField("Suspend", lambda c: bool(c.spec.suspend)),
    ],
)


SERVICES = ResourceDescriptor(
    key="services",
    label="Services",
    list_fn=_ns_list(
        "core", "list_service_for_all_namespaces", "list_namespaced_service"
    ),
    get_fn=_get("core", "read_namespaced_service"),
    delete_fn=_delete("core", "delete_namespaced_service"),
    supports_forward=True,
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Type", lambda s: s.spec.type),
        Column("Cluster IP", lambda s: s.spec.cluster_ip or "N/A"),
        Column("Ports", _ports),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField("Type", lambda s: s.spec.type),
        DetailField("Cluster IP", lambda s: s.spec.cluster_ip or "N/A"),
        DetailField("Session Affinity", lambda s: s.spec.session_affinity or "None"),
        DetailField("Ports", lambda s: [_ports(s)], "list"),
        DetailField("Selector", lambda s: fmt.key_value_pairs(s.spec.selector), "list"),
    ],
)


CONFIGMAPS = ResourceDescriptor(
    key="configmaps",
    label="ConfigMaps",
    list_fn=_ns_list(
        "core", "list_config_map_for_all_namespaces", "list_namespaced_config_map"
    ),
    get_fn=_get("core", "read_namespaced_config_map"),
    delete_fn=_delete("core", "delete_namespaced_config_map"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Keys", lambda c: len(c.data or {})),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [DetailField("Keys", lambda c: sorted((c.data or {}).keys()) or ["N/A"], "list")],
)


SECRETS = ResourceDescriptor(
    key="secrets",
    label="Secrets",
    list_fn=_ns_list("core", "list_secret_for_all_namespaces", "list_namespaced_secret"),
    get_fn=_get("core", "read_namespaced_secret"),
    delete_fn=_delete("core", "delete_namespaced_secret"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Type", lambda s: s.type),
        Column("Keys", lambda s: len(s.data or {})),
        Column("Age", _AGE),
    ],
    # Values are intentionally never shown — only key names.
    detail_fields=_common_details()
    + [
        DetailField("Type", lambda s: s.type),
        DetailField("Keys", lambda s: sorted((s.data or {}).keys()) or ["N/A"], "list"),
    ],
)


PVCS = ResourceDescriptor(
    key="persistentvolumeclaims",
    label="Persistent Volume Claims",
    list_fn=_ns_list(
        "core",
        "list_persistent_volume_claim_for_all_namespaces",
        "list_namespaced_persistent_volume_claim",
    ),
    get_fn=_get("core", "read_namespaced_persistent_volume_claim"),
    delete_fn=_delete("core", "delete_namespaced_persistent_volume_claim"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Status", lambda p: p.status.phase),
        Column("Volume", lambda p: p.spec.volume_name or "N/A"),
        Column("Capacity", lambda p: (p.status.capacity or {}).get("storage", "N/A")),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField("Status", lambda p: p.status.phase, "status"),
        DetailField("Volume", lambda p: p.spec.volume_name or "N/A"),
        DetailField(
            "Access Modes", lambda p: p.spec.access_modes or ["N/A"], "list"
        ),
    ],
)


PVS = ResourceDescriptor(
    key="persistentvolumes",
    label="Persistent Volumes",
    namespaced=False,
    list_fn=_cluster_list("core", "list_persistent_volume"),
    get_fn=_get("core", "read_persistent_volume", namespaced=False),
    delete_fn=_delete("core", "delete_persistent_volume", namespaced=False),
    columns=[
        Column("Name", _NAME),
        Column("Capacity", lambda p: (p.spec.capacity or {}).get("storage", "N/A")),
        Column("Access Modes", lambda p: ", ".join(p.spec.access_modes or [])),
        Column("Reclaim Policy", lambda p: p.spec.persistent_volume_reclaim_policy),
        Column("Status", lambda p: p.status.phase),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details(namespaced=False)
    + [
        DetailField("Capacity", lambda p: (p.spec.capacity or {}).get("storage", "N/A")),
        DetailField("Status", lambda p: p.status.phase, "status"),
        DetailField("Storage Class", lambda p: p.spec.storage_class_name or "N/A"),
    ],
)


NODES = ResourceDescriptor(
    key="nodes",
    label="Nodes",
    namespaced=False,
    list_fn=_cluster_list("core", "list_node"),
    get_fn=_get("core", "read_node", namespaced=False),
    columns=[
        Column("Name", _NAME),
        Column("Status", _node_status),
        Column("Roles", _node_roles),
        Column("Version", lambda n: n.status.node_info.kubelet_version),
        Column("Age", _AGE),
    ],
    table_conditional=[
        {"if": {"filter_query": '{status} = "Ready"'}, "color": "var(--success)"},
        {"if": {"filter_query": '{status} = "NotReady"'}, "color": "var(--danger)"},
    ],
    detail_fields=_common_details(namespaced=False)
    + [
        DetailField("Status", _node_status, "status"),
        DetailField("Roles", _node_roles),
        DetailField("Kubelet Version", lambda n: n.status.node_info.kubelet_version),
        DetailField("OS Image", lambda n: n.status.node_info.os_image),
        DetailField("Container Runtime", lambda n: n.status.node_info.container_runtime_version),
        DetailField("Architecture", lambda n: n.status.node_info.architecture),
        DetailField("Conditions", _conditions, "list"),
    ],
)


NAMESPACES = ResourceDescriptor(
    key="namespaces",
    label="Namespaces",
    namespaced=False,
    list_fn=_cluster_list("core", "list_namespace"),
    get_fn=_get("core", "read_namespace", namespaced=False),
    delete_fn=_delete("core", "delete_namespace", namespaced=False),
    columns=[
        Column("Name", _NAME),
        Column("Status", lambda n: n.status.phase),
        Column("Age", _AGE),
    ],
    table_conditional=[
        {"if": {"filter_query": '{status} = "Active"'}, "color": "var(--success)"},
        {"if": {"filter_query": '{status} = "Terminating"'}, "color": "var(--warning)"},
    ],
    detail_fields=_common_details(namespaced=False)
    + [DetailField("Status", lambda n: n.status.phase, "status")],
)


def _ingress_hosts(ing) -> str:
    hosts = [r.host for r in ing.spec.rules or [] if r.host]
    return ", ".join(hosts) or "N/A"


def _ingress_lb(ing) -> str:
    entries = []
    for ing_lb in ing.status.load_balancer.ingress or []:
        entries.append(ing_lb.ip or ing_lb.hostname or "")
    return ", ".join(e for e in entries if e) or "Pending"


def _endpoint_addresses(ep) -> list[str]:
    out = []
    for subset in ep.subsets or []:
        for addr in subset.addresses or []:
            ports = ", ".join(str(p.port) for p in subset.ports or []) or "*"
            out.append(f"{addr.ip}:{ports}")
    return out or ["N/A"]


def _event_object(ev) -> str:
    obj = ev.involved_object
    return f"{obj.kind} {obj.namespace}/{obj.name}" if obj else "N/A"


# --------------------------------------------------------------------------- #
# Network (networking.k8s.io/v1).
# --------------------------------------------------------------------------- #
INGRESSES = ResourceDescriptor(
    key="ingresses",
    label="Ingresses",
    list_fn=_ns_list(
        "networking", "list_ingress_for_all_namespaces", "list_namespaced_ingress"
    ),
    get_fn=_get("networking", "read_namespaced_ingress"),
    delete_fn=_delete("networking", "delete_namespaced_ingress"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Hosts", _ingress_hosts),
        Column("Load Balancer", _ingress_lb),
        Column("TLS", lambda i: len(i.spec.tls or [])),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField("Class Name", lambda i: i.spec.ingress_class_name or "N/A"),
        DetailField("Hosts", lambda i: [r.host for r in i.spec.rules or [] if r.host] or ["N/A"], "list"),
        DetailField("TLS", lambda i: [t.hosts for t in i.spec.tls or [] if t.hosts] or ["N/A"], "list"),
        DetailField("Load Balancer", _ingress_lb, "status"),
    ],
)

NETWORKPOLICIES = ResourceDescriptor(
    key="networkpolicies",
    label="Network Policies",
    list_fn=_ns_list(
        "networking",
        "list_network_policy_for_all_namespaces",
        "list_namespaced_network_policy",
    ),
    get_fn=_get("networking", "read_namespaced_network_policy"),
    delete_fn=_delete("networking", "delete_namespaced_network_policy"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Pod Selector", lambda p: fmt.joined_labels(p.spec.pod_selector.match_labels)),
        Column("Policy Types", lambda p: ", ".join(p.spec.policy_types or [])),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField("Pod Selector", lambda p: fmt.key_value_pairs(p.spec.pod_selector.match_labels), "list"),
        DetailField("Policy Types", lambda p: p.spec.policy_types or ["N/A"], "list"),
        DetailField("Ingress Rules", lambda p: len(p.spec.ingress or [])),
        DetailField("Egress Rules", lambda p: len(p.spec.egress or [])),
    ],
)

ENDPOINTS = ResourceDescriptor(
    key="endpoints",
    label="Endpoints",
    list_fn=_ns_list(
        "core", "list_endpoints_for_all_namespaces", "list_namespaced_endpoints"
    ),
    get_fn=_get("core", "read_namespaced_endpoints"),
    delete_fn=_delete("core", "delete_namespaced_endpoints"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Endpoints", lambda e: sum(
            len(s.addresses or []) for s in e.subsets or []
        )),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [DetailField("Addresses", _endpoint_addresses, "list")],
)


# --------------------------------------------------------------------------- #
# Config (autoscaling/v1, storage.k8s.io/v1, core/v1).
# --------------------------------------------------------------------------- #
HPAS = ResourceDescriptor(
    key="hpa",
    label="Horizontal Pod Autoscalers",
    list_fn=_ns_list(
        "autoscaling",
        "list_horizontal_pod_autoscaler_for_all_namespaces",
        "list_namespaced_horizontal_pod_autoscaler",
    ),
    get_fn=_get("autoscaling", "read_namespaced_horizontal_pod_autoscaler"),
    delete_fn=_delete("autoscaling", "delete_namespaced_horizontal_pod_autoscaler"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Target", lambda h: f"{h.spec.scale_target_ref.kind}/{h.spec.scale_target_ref.name}"),
        Column("Min", lambda h: h.spec.min_replicas or 1),
        Column("Max", lambda h: h.spec.max_replicas),
        Column("Replicas", lambda h: h.status.current_replicas),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField("Scale Target", lambda h: f"{h.spec.scale_target_ref.kind} {h.spec.scale_target_ref.name}"),
        DetailField("Min Replicas", lambda h: h.spec.min_replicas or 1),
        DetailField("Max Replicas", lambda h: h.spec.max_replicas),
        DetailField(
            "Replicas",
            lambda h: f"{h.status.current_replicas} current / {h.status.desired_replicas} desired",
        ),
    ],
)

STORAGECLASSES = ResourceDescriptor(
    key="storageclasses",
    label="Storage Classes",
    namespaced=False,
    list_fn=_cluster_list("storage", "list_storage_class"),
    get_fn=_get("storage", "read_storage_class", namespaced=False),
    delete_fn=_delete("storage", "delete_storage_class", namespaced=False),
    columns=[
        Column("Name", _NAME),
        Column("Provisioner", lambda s: s.provisioner),
        Column("Reclaim Policy", lambda s: s.reclaim_policy),
        Column("Volume Binding Mode", lambda s: s.volume_binding_mode or "N/A"),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details(namespaced=False)
    + [
        DetailField("Provisioner", lambda s: s.provisioner),
        DetailField("Reclaim Policy", lambda s: s.reclaim_policy),
        DetailField("Volume Binding Mode", lambda s: s.volume_binding_mode or "N/A"),
        DetailField("Allow Volume Expansion", lambda s: bool(s.allow_volume_expansion)),
        DetailField("Parameters", lambda s: fmt.key_value_pairs(s.parameters) or ["N/A"], "list"),
    ],
)

SERVICEACCOUNTS = ResourceDescriptor(
    key="serviceaccounts",
    label="Service Accounts",
    list_fn=_ns_list(
        "core",
        "list_service_account_for_all_namespaces",
        "list_namespaced_service_account",
    ),
    get_fn=_get("core", "read_namespaced_service_account"),
    delete_fn=_delete("core", "delete_namespaced_service_account"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Secrets", lambda s: len(s.secrets or [])),
        Column("Age", _AGE),
    ],
    detail_fields=_common_details()
    + [
        DetailField("Secrets", lambda s: [sec.name for sec in s.secrets or []] or ["N/A"], "list"),
        DetailField(
            "Image Pull Secrets",
            lambda s: [sec.name for sec in s.image_pull_secrets or []] or ["N/A"],
            "list",
        ),
        DetailField("Automount Token", lambda s: s.automount_service_account_token),
    ],
)


# --------------------------------------------------------------------------- #
# Events (core/v1) — read-only, transient.
# --------------------------------------------------------------------------- #
EVENTS = ResourceDescriptor(
    key="events",
    label="Events",
    list_fn=_ns_list("core", "list_event_for_all_namespaces", "list_namespaced_event"),
    get_fn=_get("core", "read_namespaced_event"),
    columns=[
        Column("Name", _NAME),
        Column("Namespace", _NS),
        Column("Type", lambda e: e.type),
        Column("Reason", lambda e: e.reason or "N/A"),
        Column("Object", _event_object),
        Column("Count", lambda e: e.count or 0),
        Column("Age", lambda e: fmt.age_short(e.first_timestamp or e.metadata.creation_timestamp)),
    ],
    table_conditional=[
        {"if": {"filter_query": '{type} = "Normal"'}, "color": "var(--success)"},
        {"if": {"filter_query": '{type} = "Warning"'}, "color": "var(--warning)"},
    ],
    detail_fields=_common_details()
    + [
        DetailField("Type", lambda e: e.type, "status"),
        DetailField("Reason", lambda e: e.reason or "N/A"),
        DetailField("Message", lambda e: e.message or "N/A"),
        DetailField("Object", _event_object),
        DetailField("Count", lambda e: e.count or 0),
        DetailField("Source", lambda e: e.source.component or "N/A"),
    ],
)


# Registry of implemented resources, keyed by their URL slug.
_ALL = [
    PODS, DEPLOYMENTS, DAEMONSETS, STATEFULSETS, REPLICASETS, JOBS, CRONJOBS,
    SERVICES, CONFIGMAPS, SECRETS, PVCS, PVS, NODES, NAMESPACES,
    INGRESSES, NETWORKPOLICIES, ENDPOINTS, HPAS, STORAGECLASSES,
    SERVICEACCOUNTS, EVENTS,
]
REGISTRY: dict[str, ResourceDescriptor] = {d.key: d for d in _ALL}

DEFAULT_RESOURCE = PODS.key


def get_descriptor(key: str | None) -> ResourceDescriptor | None:
    return REGISTRY.get(key or "")


def resource_from_path(pathname: str | None) -> ResourceDescriptor:
    """Resolve a URL like ``/r/pods`` to a descriptor, falling back to default."""
    key = (pathname or "").removeprefix("/r/").strip("/")
    return get_descriptor(key) or REGISTRY[DEFAULT_RESOURCE]


# --------------------------------------------------------------------------- #
# Sidebar menu definition — mirrors the full Lens navigation. Items pointing at
# a key present in REGISTRY are clickable; the rest are shown as "coming soon".
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MenuItem:
    key: str
    label: str

    @property
    def implemented(self) -> bool:
        return self.key in REGISTRY


@dataclass(frozen=True)
class MenuGroup:
    label: str
    items: tuple[MenuItem, ...] = ()  # empty => standalone, non-expandable entry
    href: str | None = None  # standalone entry that links somewhere (e.g. Helm)


def _item(label: str, key: str | None = None) -> MenuItem:
    return MenuItem(key=key or _slug(label), label=label)


MENU: tuple[MenuGroup, ...] = (
    MenuGroup(
        "Cluster",
        (
            _item("Service Accounts", "serviceaccounts"),
            _item("Events", "events"),
        ),
    ),
    MenuGroup("Nodes", (_item("Nodes", "nodes"),)),
    MenuGroup(
        "Workloads",
        (
            _item("Overview"),
            _item("Pods", "pods"),
            _item("Deployments", "deployments"),
            _item("DaemonSets", "daemonsets"),
            _item("StatefulSets", "statefulsets"),
            _item("ReplicaSets", "replicasets"),
            _item("Replication Controllers"),
            _item("Jobs", "jobs"),
            _item("CronJobs", "cronjobs"),
        ),
    ),
    MenuGroup(
        "Config",
        (
            _item("ConfigMaps", "configmaps"),
            _item("Secrets", "secrets"),
            _item("Resource Quotas"),
            _item("Limit Ranges"),
            _item("HPA", "hpa"),
            _item("Pod Disruption Budgets"),
            _item("Priority Classes"),
            _item("Runtime Classes"),
            _item("Leases"),
            _item("Mutating Webhook Configs"),
            _item("Validating Webhook Configs"),
        ),
    ),
    MenuGroup(
        "Network",
        (
            _item("Services", "services"),
            _item("Endpoints", "endpoints"),
            _item("Ingresses", "ingresses"),
            _item("Ingress Classes"),
            _item("Network Policies", "networkpolicies"),
            _item("Port Forwarding"),
        ),
    ),
    MenuGroup(
        "Storage",
        (
            _item("Persistent Volume Claims", "persistentvolumeclaims"),
            _item("Persistent Volumes", "persistentvolumes"),
            _item("Storage Classes", "storageclasses"),
        ),
    ),
    MenuGroup("Namespaces", (_item("Namespaces", "namespaces"),)),
    MenuGroup("Helm", href="/helm"),
    MenuGroup("Access Control"),
    MenuGroup("Custom Resources", href="/crd"),
)
