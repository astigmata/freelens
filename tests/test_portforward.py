"""Tests for port-forward target resolution and the listener manager.

None of these touch a real cluster: ``list_ports`` / ``resolve_forward_target``
run against fake API objects, and the manager only ever opens a real TCP socket
on loopback — the Kubernetes stream is reached lazily, on an actual connection,
so starting and stopping a forward needs no cluster.
"""

from types import SimpleNamespace

import pytest

from freelens import config
from freelens.k8s import operations as ops
from freelens.k8s.registry import REGISTRY
from freelens.portforward import MANAGER


# --------------------------------------------------------------------------- #
# Fakes mimicking the kubernetes client object shapes.
# --------------------------------------------------------------------------- #
def _pod(name, containers, phase="Running", ready=True, labels=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace="default", labels=labels or {}),
        spec=SimpleNamespace(containers=containers),
        status=SimpleNamespace(
            phase=phase,
            conditions=[SimpleNamespace(type="Ready", status="True" if ready else "False")],
        ),
    )


def _container(name, ports):
    return SimpleNamespace(name=name, ports=ports)


def _port(container_port, name=None, protocol="TCP"):
    return SimpleNamespace(container_port=container_port, name=name, protocol=protocol)


class _FakeCore:
    def __init__(self, pod=None, service=None, pods=None):
        self._pod = pod
        self._service = service
        self._pods = pods or []

    def read_namespaced_pod(self, name, namespace):
        return self._pod

    def read_namespaced_service(self, name, namespace):
        return self._service

    def list_namespaced_pod(self, namespace, label_selector=None):
        return SimpleNamespace(items=self._pods)


def _clients(core):
    return SimpleNamespace(core=core)


# --------------------------------------------------------------------------- #
# Registry wiring.
# --------------------------------------------------------------------------- #
def test_only_pods_and_services_support_forward():
    assert REGISTRY["pods"].supports_forward is True
    assert REGISTRY["services"].supports_forward is True
    assert REGISTRY["deployments"].supports_forward is False
    assert REGISTRY["configmaps"].supports_forward is False


# --------------------------------------------------------------------------- #
# list_ports.
# --------------------------------------------------------------------------- #
def test_list_ports_for_pod_skips_udp_and_labels_container():
    pod = _pod("web", [_container("app", [_port(8080, "http"), _port(53, "dns", "UDP")])])
    options = ops.list_ports(_clients(_FakeCore(pod=pod)), "pods", "web", "default")
    assert options == [{"label": "8080 (http) — app", "value": 8080}]


def test_list_ports_for_service():
    svc = SimpleNamespace(
        spec=SimpleNamespace(ports=[
            SimpleNamespace(port=443, name="https", protocol="TCP"),
            SimpleNamespace(port=80, name=None, protocol="TCP"),
        ])
    )
    options = ops.list_ports(_clients(_FakeCore(service=svc)), "services", "svc", "default")
    assert options == [
        {"label": "443 (https)", "value": 443},
        {"label": "80", "value": 80},
    ]


# --------------------------------------------------------------------------- #
# resolve_forward_target.
# --------------------------------------------------------------------------- #
def test_resolve_pod_target_is_passthrough():
    assert ops.resolve_forward_target(_clients(_FakeCore()), "pods", "web", "default", 8080) == (
        "web", 8080,
    )


def test_resolve_service_translates_named_target_port_to_ready_pod():
    svc = SimpleNamespace(spec=SimpleNamespace(
        ports=[SimpleNamespace(port=80, target_port="http")],
        selector={"app": "web"},
    ))
    ready = _pod("web-1", [_container("app", [_port(8080, "http")])], ready=True)
    not_ready = _pod("web-0", [_container("app", [_port(8080, "http")])], ready=False)
    core = _FakeCore(service=svc, pods=[not_ready, ready])
    assert ops.resolve_forward_target(_clients(core), "services", "web", "default", 80) == (
        "web-1", 8080,
    )


def test_resolve_service_uses_numeric_target_port():
    svc = SimpleNamespace(spec=SimpleNamespace(
        ports=[SimpleNamespace(port=80, target_port=9000)],
        selector={"app": "web"},
    ))
    core = _FakeCore(service=svc, pods=[_pod("web-0", [_container("app", [])])])
    assert ops.resolve_forward_target(_clients(core), "services", "web", "default", 80) == (
        "web-0", 9000,
    )


def test_resolve_service_defaults_target_port_to_port():
    svc = SimpleNamespace(spec=SimpleNamespace(
        ports=[SimpleNamespace(port=80, target_port=None)],
        selector={"app": "web"},
    ))
    core = _FakeCore(service=svc, pods=[_pod("web-0", [_container("app", [])])])
    assert ops.resolve_forward_target(_clients(core), "services", "web", "default", 80) == (
        "web-0", 80,
    )


def test_resolve_service_without_ready_pod_errors():
    svc = SimpleNamespace(spec=SimpleNamespace(
        ports=[SimpleNamespace(port=80, target_port=80)], selector={"app": "web"},
    ))
    not_ready = _pod("web-0", [_container("app", [])], phase="Pending", ready=False)
    core = _FakeCore(service=svc, pods=[not_ready])
    with pytest.raises(ValueError, match="no ready backing pod"):
        ops.resolve_forward_target(_clients(core), "services", "web", "default", 80)


def test_resolve_service_without_any_pod_errors():
    svc = SimpleNamespace(spec=SimpleNamespace(
        ports=[SimpleNamespace(port=80, target_port=80)], selector={"app": "web"},
    ))
    core = _FakeCore(service=svc, pods=[])
    with pytest.raises(ValueError, match="no ready backing pod"):
        ops.resolve_forward_target(_clients(core), "services", "web", "default", 80)


def test_resolve_service_without_selector_errors():
    svc = SimpleNamespace(spec=SimpleNamespace(
        ports=[SimpleNamespace(port=80, target_port=80)], selector=None,
    ))
    with pytest.raises(ValueError, match="selector"):
        ops.resolve_forward_target(_clients(_FakeCore(service=svc)), "services", "s", "default", 80)


def test_resolve_service_unknown_port_errors():
    svc = SimpleNamespace(spec=SimpleNamespace(
        ports=[SimpleNamespace(port=80, target_port=80)], selector={"a": "b"},
    ))
    with pytest.raises(ValueError, match="no port"):
        ops.resolve_forward_target(_clients(_FakeCore(service=svc)), "services", "s", "default", 443)


# --------------------------------------------------------------------------- #
# Manager lifecycle.
# --------------------------------------------------------------------------- #
def test_manager_start_binds_loopback_then_stop_removes_it():
    fwd = MANAGER.start(object(), "pods", "web", "default", "web", 8080)
    try:
        assert fwd.address.startswith("127.0.0.1:")
        assert fwd.local_port > 0
        assert any(f.id == fwd.id for f in MANAGER.list())
    finally:
        stopped = MANAGER.stop(fwd.id)
    assert stopped is fwd
    assert all(f.id != fwd.id for f in MANAGER.list())
    # Stopping an unknown id is a no-op.
    assert MANAGER.stop(fwd.id) is None


def test_manager_refuses_non_loopback_bind(monkeypatch):
    monkeypatch.setattr(config, "FORWARD_BIND_HOST", "0.0.0.0")
    monkeypatch.setattr(config, "ALLOW_INSECURE", False)
    with pytest.raises(ValueError, match="non-loopback"):
        MANAGER.start(object(), "pods", "web", "default", "web", 8080)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
