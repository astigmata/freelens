"""Sanity checks for the curated Helm chart catalog."""

from freelens.k8s.helm_catalog import CATALOG, CATALOG_BY_KEY


def test_keys_are_unique():
    keys = [e.key for e in CATALOG]
    assert len(keys) == len(set(keys))
    assert set(CATALOG_BY_KEY) == set(keys)


def test_entries_are_well_formed():
    assert CATALOG, "catalog should not be empty"
    for e in CATALOG:
        assert e.key and e.label and e.description
        assert e.chart and e.release and e.namespace
        assert e.repo_url.startswith(("http://", "https://", "oci://"))
        # With --repo, helm wants a bare chart name, so no slash prefix here.
        assert "/" not in e.chart
