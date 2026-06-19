"""Tests for the CRD discovery / instance helpers (typed objects are mocked)."""

from types import SimpleNamespace

from freelens.k8s import crd


def _crd(group, kind, plural, scope, versions):
    """Build a fake CustomResourceDefinition object like the client returns."""
    return SimpleNamespace(
        spec=SimpleNamespace(
            group=group,
            scope=scope,
            names=SimpleNamespace(plural=plural, kind=kind),
            versions=[SimpleNamespace(name=n, storage=s) for n, s in versions],
        )
    )


def _clients(crds):
    items = SimpleNamespace(items=crds)
    apiext = SimpleNamespace(list_custom_resource_definition=lambda: items)
    return SimpleNamespace(apiext=apiext)


def test_list_crds_prefers_storage_version_and_sorts():
    clients = _clients(
        [
            _crd("metallb.io", "IPAddressPool", "ipaddresspools", "Namespaced",
                 [("v1beta1", True)]),
            _crd("metallb.io", "BGPPeer", "bgppeers", "Namespaced",
                 [("v1beta1", False), ("v1beta2", True)]),
            _crd("x.io", "Widget", "widgets", "Cluster", [("v1", True)]),
        ]
    )
    result = crd.list_crds(clients)

    # Sorted by (group, kind): BGPPeer before IPAddressPool, then Widget.
    assert [c["kind"] for c in result] == ["BGPPeer", "IPAddressPool", "Widget"]
    # Storage version wins over a merely-served one.
    assert result[0]["version"] == "v1beta2"
    # Scope maps to the namespaced flag.
    assert result[0]["namespaced"] is True
    assert result[2]["namespaced"] is False


def test_list_crds_skips_versionless():
    clients = _clients([_crd("x.io", "Empty", "empties", "Cluster", [])])
    assert crd.list_crds(clients) == []


def test_to_rows_extracts_name_namespace_age():
    items = [
        {"metadata": {"name": "demo-pool", "namespace": "metallb-system",
                      "creationTimestamp": None}},
        {"metadata": {"name": "cluster-thing"}},  # no namespace / timestamp
    ]
    rows = crd.to_rows(items)
    assert rows[0]["name"] == "demo-pool"
    assert rows[0]["namespace"] == "metallb-system"
    assert rows[0]["age"] == "N/A"
    assert rows[1]["namespace"] == ""
