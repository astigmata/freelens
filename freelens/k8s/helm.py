"""Helm release management via the ``helm`` CLI.

Helm releases are not Kubernetes API objects, so they don't fit the
``ResourceDescriptor`` registry the rest of the app is built on. Instead we shell
out to the ``helm`` binary, which reads the very same kubeconfig / current
context as the Kubernetes client, and parse its JSON output. Keeping every helm
invocation funnelled through :func:`_run` means there is one auditable place for
process handling, timeouts and error surfacing.
"""

import json
import logging
import shutil
import subprocess

log = logging.getLogger(__name__)

HELM_BIN = "helm"
_TIMEOUT = 120  # seconds — install/upgrade can pull charts over the network


class HelmError(RuntimeError):
    """Raised when a helm invocation fails or helm is unavailable."""


def available() -> bool:
    """True when the ``helm`` binary is on PATH."""
    return shutil.which(HELM_BIN) is not None


def _impersonation_flags() -> list[str]:
    """Global helm flags to run as the authenticated user, for imputability.

    Mirrors the API-server impersonation used by the Kubernetes client so helm
    actions are attributed to the real person, not the app's ServiceAccount.
    Imported lazily to avoid a circular import with the auth layer.
    """
    from .. import config
    from ..auth import current_identity

    identity = current_identity()
    if not (config.IMPERSONATE and identity and not identity.is_local):
        return []
    flags = ["--kube-as-user", identity.user]
    for group in identity.groups:
        flags += ["--kube-as-group", group]
    return flags


def _run(args: list[str], *, as_json: bool = False, stdin: str | None = None):
    if not available():
        raise HelmError("The 'helm' CLI was not found on PATH.")
    try:
        proc = subprocess.run(
            [HELM_BIN, *_impersonation_flags(), *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            input=stdin,
        )
    except subprocess.TimeoutExpired as exc:
        raise HelmError(f"helm timed out: helm {' '.join(args)}") from exc

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "unknown error").strip()
        log.warning("helm %s failed: %s", " ".join(args), msg)
        raise HelmError(msg)

    if as_json:
        return json.loads(proc.stdout or "null")
    return proc.stdout


# --------------------------------------------------------------------------- #
# Read operations.
# --------------------------------------------------------------------------- #
def list_releases(namespace: str = "all") -> list[dict]:
    """List installed releases as a list of dicts (helm list --output json)."""
    args = ["list", "--output", "json"]
    if namespace and namespace != "all":
        args += ["--namespace", namespace]
    else:
        args.append("--all-namespaces")
    return _run(args, as_json=True) or []


def release_values(name: str, namespace: str) -> str:
    """User-supplied + computed values for a release, as YAML."""
    return _run(["get", "values", name, "--namespace", namespace, "--all"])


def release_history(name: str, namespace: str) -> list[dict]:
    return _run(
        ["history", name, "--namespace", namespace, "--output", "json"], as_json=True
    ) or []


def release_manifest(name: str, namespace: str) -> str:
    return _run(["get", "manifest", name, "--namespace", namespace])


def repo_list() -> list[dict]:
    """Configured chart repositories (empty when none are configured)."""
    try:
        return _run(["repo", "list", "--output", "json"], as_json=True) or []
    except HelmError:
        return []


# --------------------------------------------------------------------------- #
# Write operations.
# --------------------------------------------------------------------------- #
def install(
    release: str,
    chart: str,
    namespace: str,
    version: str = "",
    values_yaml: str = "",
    create_namespace: bool = True,
    repo_url: str = "",
) -> str:
    """Install a chart as a new release. ``values_yaml`` is fed via stdin.

    When ``repo_url`` is given, ``chart`` is the bare chart name and helm pulls it
    from that repository (``--repo``) without it having to be added first.
    """
    if repo_url:
        # With --repo, helm wants the bare chart name; tolerate a "repo/chart"
        # prefix so the user can paste either form.
        chart = chart.rsplit("/", 1)[-1]
    args = ["install", release, chart, "--namespace", namespace]
    if repo_url:
        args += ["--repo", repo_url]
    if version:
        args += ["--version", version]
    if create_namespace:
        args.append("--create-namespace")
    stdin = None
    if values_yaml and values_yaml.strip():
        args += ["--values", "-"]
        stdin = values_yaml
    return _run(args, stdin=stdin)


def upgrade(
    release: str,
    chart: str,
    namespace: str,
    version: str = "",
    values_yaml: str = "",
    repo_url: str = "",
) -> str:
    """Upgrade a release, installing it if it does not yet exist (--install)."""
    if repo_url:
        chart = chart.rsplit("/", 1)[-1]
    args = ["upgrade", "--install", release, chart, "--namespace", namespace]
    if repo_url:
        args += ["--repo", repo_url]
    if version:
        args += ["--version", version]
    stdin = None
    if values_yaml and values_yaml.strip():
        args += ["--values", "-"]
        stdin = values_yaml
    return _run(args, stdin=stdin)


def uninstall(name: str, namespace: str) -> str:
    return _run(["uninstall", name, "--namespace", namespace])


def rollback(name: str, namespace: str, revision: str | int = "") -> str:
    """Roll a release back to ``revision`` (or the previous one when blank)."""
    args = ["rollback", name]
    if revision not in ("", None):
        args.append(str(revision))
    args += ["--namespace", namespace]
    return _run(args)
