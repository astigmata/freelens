"""Tests for the declarative registry and formatters (no cluster required)."""

import datetime
from types import SimpleNamespace

import pytest

from freelens.k8s import formatters as fmt
from freelens.k8s.registry import (
    DEFAULT_RESOURCE,
    REGISTRY,
    Column,
    resource_from_path,
)


def test_column_id_slugifies_label():
    assert Column("Up-to-date", lambda o: None).id == "up_to_date"
    assert Column("QoS", lambda o: None).id == "qos"


def test_resource_from_path_resolves_and_falls_back():
    assert resource_from_path("/r/deployments").key == "deployments"
    assert resource_from_path("/r/nodes").key == "nodes"
    assert resource_from_path("/").key == DEFAULT_RESOURCE
    assert resource_from_path("/r/unknown").key == DEFAULT_RESOURCE


def test_every_resource_has_a_name_column():
    for descriptor in REGISTRY.values():
        assert "name" in {col.id for col in descriptor.columns}


def test_namespaced_resources_expose_a_namespace_column():
    for descriptor in REGISTRY.values():
        ids = {col.id for col in descriptor.columns}
        if descriptor.namespaced:
            assert "namespace" in ids, descriptor.key
        else:
            assert "namespace" not in ids, descriptor.key


def test_cluster_scoped_resources_are_marked_non_namespaced():
    for key in ("nodes", "namespaces", "persistentvolumes"):
        assert REGISTRY[key].namespaced is False


def test_write_actions_are_wired_to_the_expected_resources():
    assert REGISTRY["deployments"].action("scale").needs_value is True
    assert REGISTRY["deployments"].action("restart") is not None
    assert REGISTRY["pods"].action("delete").destructive is True
    assert REGISTRY["pods"].supports_logs is True
    # No accidental write actions on a read-only resource.
    assert REGISTRY["configmaps"].actions == ()


def test_age_short_handles_days_and_hours():
    now = datetime.datetime.now(datetime.timezone.utc)
    assert fmt.age_short(now - datetime.timedelta(days=3)) == "3d"
    assert fmt.age_short(now - datetime.timedelta(hours=5)) == "5h"
    assert fmt.age_short(None) == "N/A"


def test_age_short_uses_minutes_and_seconds_under_an_hour():
    now = datetime.datetime.now(datetime.timezone.utc)
    # A couple of seconds of slack so the elapsed clock time doesn't tip a
    # boundary value into the next-lower unit.
    assert fmt.age_short(now - datetime.timedelta(minutes=4, seconds=10)) == "4m10s"
    assert fmt.age_short(now - datetime.timedelta(seconds=8)) == "8s"
    assert fmt.age_short(now - datetime.timedelta(minutes=59, seconds=2)) == "59m2s"


def test_age_long_includes_days_hours_minutes():
    now = datetime.datetime.now(datetime.timezone.utc)
    result = fmt.age_long(now - datetime.timedelta(days=1, hours=2, minutes=3))
    assert result == "1d 2h 3m ago"


def test_key_value_pairs_sorted_with_fallback():
    assert fmt.key_value_pairs({"b": "2", "a": "1"}) == ["a: 1", "b: 2"]
    assert fmt.key_value_pairs(None) == ["N/A"]


def test_pod_columns_render_against_a_fake_object():
    pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="web-0",
            namespace="default",
            owner_references=None,
            creation_timestamp=datetime.datetime.now(datetime.timezone.utc),
        ),
        spec=SimpleNamespace(containers=[1, 2], node_name="node-1"),
        status=SimpleNamespace(
            container_statuses=[SimpleNamespace(ready=True, restart_count=0)],
            qos_class="BestEffort",
            phase="Running",
        ),
    )
    row = {col.id: str(col.accessor(pod)) for col in REGISTRY["pods"].columns}
    assert row["name"] == "web-0"
    assert row["containers"] == "1/2"
    assert row["status"] == "Running"
    assert row["controlled_by"] == "N/A"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
