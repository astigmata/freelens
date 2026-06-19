"""Tests for bulk-delete wiring and the log line filter."""

from freelens.callbacks.details import _filter_lines
from freelens.k8s.registry import REGISTRY


def test_filter_lines_keeps_matching_case_insensitive():
    text = "GET /a 200\nPOST /b 500\nget /c 404"
    assert _filter_lines(text, "get") == "GET /a 200\nget /c 404"


def test_filter_lines_no_needle_returns_all():
    text = "line1\nline2"
    assert _filter_lines(text, None) == text
    assert _filter_lines(text, "") == text


def test_filter_lines_no_match_message():
    assert _filter_lines("a\nb", "zzz") == "(no matching lines)"


def test_common_resources_are_bulk_deletable():
    for key in ("pods", "deployments", "services", "configmaps", "namespaces"):
        assert REGISTRY[key].delete_fn is not None, key


def test_nodes_are_not_deletable():
    # Deleting nodes from a bulk checkbox would be too dangerous.
    assert REGISTRY["nodes"].delete_fn is None


def test_only_pods_support_exec():
    assert REGISTRY["pods"].supports_exec is True
    assert REGISTRY["deployments"].supports_exec is False
