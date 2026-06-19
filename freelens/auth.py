"""Authentication, identity propagation and CSRF defence.

Freelens is meant to run behind an authenticating reverse proxy (oauth2-proxy /
OIDC) that performs the login and injects the user's identity as request headers.
This module turns those headers into a verified :class:`Identity`, refuses every
unauthenticated request, and propagates the identity (via ``flask.g``) to the
Kubernetes layer so actions are impersonated and audited per user.

Two modes (``FREELENS_AUTH_MODE``):

* ``proxy``    — trust identity headers, but only from a configured trusted proxy.
                 This is the mode required for any HDS / health-data deployment.
* ``disabled`` — no auth; a synthetic local identity is used. Local dev only; a
                 loud warning is emitted at startup.
"""

import ipaddress
import logging
import os
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

from flask import Flask, abort, g, has_request_context, request

from . import config
from .k8s import client as k8s_client

log = logging.getLogger(__name__)

# Paths reachable without authentication: static assets and the liveness probe.
_PUBLIC_PREFIXES = ("/assets/",)
_PUBLIC_PATHS = ("/healthz",)

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_LOCAL_IDENTITY = None  # set lazily for disabled mode


@dataclass(frozen=True)
class Identity:
    user: str
    email: str = ""
    groups: tuple[str, ...] = ()

    @property
    def is_local(self) -> bool:
        return self.user == "local-dev"


def _local_identity() -> Identity:
    global _LOCAL_IDENTITY
    if _LOCAL_IDENTITY is None:
        _LOCAL_IDENTITY = Identity(user="local-dev", email="local@localhost")
    return _LOCAL_IDENTITY


def _remote_is_trusted_proxy() -> bool:
    """True when the request comes from a configured trusted proxy."""
    if not config.TRUSTED_PROXIES:
        return False
    try:
        remote = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    for entry in config.TRUSTED_PROXIES:
        try:
            if remote in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def identity_from_request() -> Identity | None:
    """Resolve the caller's identity, or ``None`` when unauthenticated.

    In ``proxy`` mode the identity headers are honoured only when the request
    actually originates from a trusted proxy, so a client talking to the app
    directly cannot forge them.
    """
    if config.AUTH_MODE == "disabled":
        return _local_identity()

    if config.AUTH_MODE == "proxy":
        if not _remote_is_trusted_proxy():
            return None
        user = request.headers.get(config.HEADER_USER, "").strip()
        if not user:
            return None
        groups = request.headers.get(config.HEADER_GROUPS, "")
        return Identity(
            user=user,
            email=request.headers.get(config.HEADER_EMAIL, "").strip(),
            groups=tuple(g for g in (s.strip() for s in groups.split(",")) if g),
        )

    # Unknown mode: fail closed.
    log.error("Unknown FREELENS_AUTH_MODE=%r; refusing all requests.", config.AUTH_MODE)
    return None


# --------------------------------------------------------------------------- #
# Origin / CSRF helpers (shared with the terminal WebSocket guard).
# --------------------------------------------------------------------------- #
def expected_hosts() -> set[str]:
    """Host[:port] values considered same-origin for the current request.

    Includes the proxy-forwarded host so that, behind oauth2-proxy, the external
    Origin still matches.
    """
    hosts = {request.host}
    fwd = request.headers.get("X-Forwarded-Host")
    if fwd:
        hosts.add(fwd.split(",")[0].strip())
    for origin in config.ALLOWED_ORIGINS:
        netloc = urlparse(origin).netloc
        if netloc:
            hosts.add(netloc)
    return {h for h in hosts if h}


def origin_allowed() -> bool:
    """True when the request's Origin is same-origin or allow-listed.

    A missing Origin on a state-changing request is rejected (CSRF defence);
    browsers send Origin on cross-site and same-site state-changing requests.
    """
    origin = request.headers.get("Origin")
    if not origin:
        return False
    if origin in config.ALLOWED_ORIGINS:
        return True
    return urlparse(origin).netloc in expected_hosts()


# --------------------------------------------------------------------------- #
# Wiring.
# --------------------------------------------------------------------------- #
def register_auth(server: Flask) -> None:
    """Install the auth guard, CSRF check, secret key and health endpoint."""
    server.secret_key = config.SECRET_KEY or os.urandom(32)
    # Harden the session cookie (used if integrated OIDC is added later).
    server.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=config.AUTH_MODE != "disabled",
    )

    if config.AUTH_MODE == "disabled":
        log.warning(
            "================================================================\n"
            " FREELENS_AUTH_MODE=disabled — NO AUTHENTICATION.\n"
            " This is for LOCAL DEVELOPMENT ONLY and is NOT HDS-compliant.\n"
            " Set FREELENS_AUTH_MODE=proxy behind an OIDC reverse proxy.\n"
            "================================================================"
        )

    @server.route("/healthz")
    def _healthz():
        return {"status": "ok"}

    @server.before_request
    def _guard():
        path = request.path
        if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
            return None

        identity = identity_from_request()
        if identity is None:
            abort(401)
        g.identity = identity

        # CSRF: state-changing requests must carry a same-origin Origin.
        if request.method in _MUTATING_METHODS and not origin_allowed():
            log.warning("Blocked cross-origin %s %s (Origin=%r)",
                        request.method, path, request.headers.get("Origin"))
            abort(403)
        return None


def print_startup_banner(host: str, port: int) -> None:
    """Print a hard-to-miss banner describing the security posture at startup.

    Goes to stderr (not the logger) so it stands out even when log output is
    noisy, and shows the exact URL and whether authentication is on.
    """
    url = f"http://{host}:{port}"
    if config.AUTH_MODE == "disabled":
        scope = "loopback only" if host in ("127.0.0.1", "localhost", "::1") else host
        lines = [
            "FREELENS_AUTH_MODE=disabled  —  NO AUTHENTICATION",
            "",
            f"Serving on {url}  ({scope})",
            "Anyone who can reach this address has FULL control of the cluster.",
            "Local development ONLY — this is NOT HDS-compliant.",
            "For a shared/remote deployment set FREELENS_AUTH_MODE=proxy behind",
            "an OIDC reverse proxy (see deploy/hds/).",
        ]
        border_char = "!"
    else:
        lines = [
            f"FREELENS_AUTH_MODE={config.AUTH_MODE}  —  authentication enforced",
            f"Serving on {url}",
            "Identity is taken from the trusted reverse proxy; direct access is 401.",
        ]
        border_char = "="

    width = max(len(line) for line in lines) + 4
    border = border_char * width
    print(border, file=sys.stderr)
    for line in lines:
        print(f"{border_char} {line.ljust(width - 4)} {border_char}", file=sys.stderr)
    print(border, file=sys.stderr, flush=True)


def current_identity() -> Identity | None:
    """The authenticated identity for the in-flight request, if any."""
    if not has_request_context():
        return None
    return getattr(g, "identity", None)


def active_clients() -> k8s_client.Clients:
    """Kubernetes clients for the current user.

    In proxy mode (with impersonation on) the clients carry Impersonate headers
    so the API server enforces the user's RBAC and audits the real actor. In
    disabled mode, or without impersonation, the shared service-account clients
    are used.
    """
    identity = current_identity()
    if config.IMPERSONATE and identity is not None and not identity.is_local:
        return k8s_client.get_user_clients(identity.user, identity.groups)
    return k8s_client.get_clients()
