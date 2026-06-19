"""Tests for the helm CLI wrapper — argument construction and output parsing.

These stub out ``subprocess.run`` so they assert how we invoke helm without
needing a binary or a cluster (the live lifecycle is exercised separately).
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

from freelens.k8s import helm


class _Calls(list):
    """A list that also carries the stdout the fake subprocess should return."""

    stdout_value = ""


@pytest.fixture
def fake_helm(monkeypatch):
    """Make helm appear available and capture the args passed to subprocess."""
    calls = _Calls()

    def fake_run(cmd, **kwargs):
        calls.append(SimpleNamespace(cmd=cmd, kwargs=kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=calls.stdout_value, stderr="")

    monkeypatch.setattr(helm.shutil, "which", lambda _: "/usr/local/bin/helm")
    monkeypatch.setattr(helm.subprocess, "run", fake_run)
    return calls


def test_unavailable_raises(monkeypatch):
    monkeypatch.setattr(helm.shutil, "which", lambda _: None)
    assert helm.available() is False
    with pytest.raises(helm.HelmError):
        helm.list_releases()


def test_list_all_namespaces(fake_helm):
    fake_helm.stdout_value = json.dumps([{"name": "a", "namespace": "default"}])
    releases = helm.list_releases("all")
    assert releases == [{"name": "a", "namespace": "default"}]
    assert "--all-namespaces" in fake_helm[0].cmd
    assert "--namespace" not in fake_helm[0].cmd


def test_list_single_namespace(fake_helm):
    fake_helm.stdout_value = "[]"
    helm.list_releases("demo")
    assert fake_helm[0].cmd[-2:] == ["--namespace", "demo"]


def test_install_passes_values_via_stdin(fake_helm):
    fake_helm.stdout_value = "deployed"
    helm.install("rel", "repo/chart", "ns", version="1.2.3",
                 values_yaml="key: val", create_namespace=True)
    cmd = fake_helm[0].cmd
    assert cmd[:3] == ["helm", "install", "rel"]
    assert "repo/chart" in cmd
    assert ["--version", "1.2.3"] == cmd[cmd.index("--version"):cmd.index("--version") + 2]
    assert "--create-namespace" in cmd
    assert "--values" in cmd and cmd[-1] == "-"
    assert fake_helm[0].kwargs["input"] == "key: val"


def test_install_with_repo_url_uses_repo_flag(fake_helm):
    fake_helm.stdout_value = "deployed"
    helm.install("metallb", "metallb", "metallb-system",
                 version="0.16.1", repo_url="https://metallb.github.io/metallb")
    cmd = fake_helm[0].cmd
    assert cmd[:3] == ["helm", "install", "metallb"]
    i = cmd.index("--repo")
    assert cmd[i + 1] == "https://metallb.github.io/metallb"


def test_install_with_repo_url_strips_chart_prefix(fake_helm):
    fake_helm.stdout_value = "deployed"
    # A "repo/chart" prefix is tolerated when --repo is given: helm wants the
    # bare chart name, so only "metallb" should be passed as the chart argument.
    helm.install("metallb", "metallb/metallb", "metallb-system",
                 repo_url="https://metallb.github.io/metallb")
    cmd = fake_helm[0].cmd
    assert cmd[:4] == ["helm", "install", "metallb", "metallb"]
    assert "metallb/metallb" not in cmd


def test_install_without_values_has_no_stdin(fake_helm):
    fake_helm.stdout_value = "deployed"
    helm.install("rel", "repo/chart", "ns")
    cmd = fake_helm[0].cmd
    assert "--values" not in cmd
    assert fake_helm[0].kwargs["input"] is None


def test_rollback_with_and_without_revision(fake_helm):
    fake_helm.stdout_value = "rolled back"
    helm.rollback("rel", "ns", 3)
    assert "3" in fake_helm[0].cmd

    fake_helm.clear()
    fake_helm.stdout_value = "rolled back"
    helm.rollback("rel", "ns", "")
    # No revision token between the release name and the namespace flag.
    cmd = fake_helm[0].cmd
    assert cmd[cmd.index("rel") + 1] == "--namespace"


def test_failure_surfaces_stderr(monkeypatch):
    monkeypatch.setattr(helm.shutil, "which", lambda _: "/usr/local/bin/helm")
    monkeypatch.setattr(
        helm.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom"),
    )
    with pytest.raises(helm.HelmError, match="boom"):
        helm.uninstall("rel", "ns")
