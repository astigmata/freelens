"""Application settings, overridable via environment variables."""

import os

HOST = os.environ.get("FREELENS_HOST", "127.0.0.1")
PORT = int(os.environ.get("FREELENS_PORT", "8050"))
DEBUG = os.environ.get("FREELENS_DEBUG", "false").lower() == "true"

# Page size for resource tables.
TABLE_PAGE_SIZE = int(os.environ.get("FREELENS_TABLE_PAGE_SIZE", "15"))

# Extra browser origins (scheme://host[:port]) allowed to open the pod-terminal
# WebSocket, on top of same-origin requests. Comma-separated. Used to defend the
# /ws/exec endpoint against Cross-Site WebSocket Hijacking. Empty = same-origin
# only, which is the right default.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("FREELENS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]


def _csv(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


# --------------------------------------------------------------------------- #
# Authentication & imputability.
# --------------------------------------------------------------------------- #
# "proxy"    — trust identity headers injected by an authenticating reverse proxy
#              (oauth2-proxy / OIDC). REQUIRED for any HDS / health-data use.
# "disabled" — no authentication; a synthetic local identity is used. Local dev
#              ONLY. The app logs a loud warning at startup in this mode.
AUTH_MODE = os.environ.get("FREELENS_AUTH_MODE", "disabled").strip().lower()

# CIDRs / IPs of the reverse proxy(ies) allowed to set the identity headers. In
# "proxy" mode, identity headers are honoured ONLY from these sources, so they
# cannot be spoofed by a client talking to the app directly.
TRUSTED_PROXIES = _csv("FREELENS_TRUSTED_PROXIES")

# Header names injected by the proxy (oauth2-proxy defaults).
HEADER_USER = os.environ.get("FREELENS_HEADER_USER", "X-Auth-Request-User")
HEADER_EMAIL = os.environ.get("FREELENS_HEADER_EMAIL", "X-Auth-Request-Email")
HEADER_GROUPS = os.environ.get("FREELENS_HEADER_GROUPS", "X-Auth-Request-Groups")

# Flask session signing key. Generated per-process if unset (fine for proxy mode,
# where sessions are not the source of truth). Set it to a stable secret to keep
# sessions valid across restarts.
SECRET_KEY = os.environ.get("FREELENS_SECRET_KEY", "")

# Forward the authenticated user to the Kubernetes API server via impersonation
# (Impersonate-User/-Group), so RBAC and the API server audit log attribute every
# action to the real person. The app's ServiceAccount needs the `impersonate`
# verb. Defaults on in proxy mode.
IMPERSONATE = os.environ.get(
    "FREELENS_IMPERSONATE", "true" if AUTH_MODE == "proxy" else "false"
).lower() == "true"

# Optional file for the JSON audit trail. When empty, audit events go to stdout
# (capture them at the platform level into an immutable sink).
AUDIT_FILE = os.environ.get("FREELENS_AUDIT_FILE", "").strip()

# Escape hatch: allow running with AUTH_MODE=disabled while bound to a non-loopback
# address. Off by default — the app refuses such a configuration so an
# unauthenticated instance can't be exposed on the network by accident. Only set
# this when the network is already isolated by other means.
ALLOW_INSECURE = os.environ.get("FREELENS_ALLOW_INSECURE", "false").lower() == "true"
