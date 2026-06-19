"""Immutable, structured audit trail for security-relevant actions.

Audit events are emitted as one JSON object per line on a dedicated logger
(``freelens.audit``), kept separate from the operational application logs. Each
event records *who* (the authenticated actor), *what* (action + target), *from
where* (source IP), *when* and the *result* — the minimum needed for the
imputability HDS requires.

Configure ``FREELENS_AUDIT_FILE`` to write to a file; otherwise events go to
stdout, to be shipped into an immutable/append-only sink at the platform level.
"""

import datetime
import json
import logging

from flask import g, has_request_context, request

from . import config

_audit = logging.getLogger("freelens.audit")


def init_audit() -> None:
    """Configure the dedicated audit logger once, at startup."""
    _audit.setLevel(logging.INFO)
    _audit.propagate = False  # keep audit out of the noisy app log stream
    if _audit.handlers:
        return
    handler: logging.Handler
    if config.AUDIT_FILE:
        handler = logging.FileHandler(config.AUDIT_FILE)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _audit.addHandler(handler)


def _actor() -> dict:
    identity = getattr(g, "identity", None) if has_request_context() else None
    src = ""
    if has_request_context():
        src = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    return {
        "actor": getattr(identity, "user", "anonymous"),
        "actor_email": getattr(identity, "email", ""),
        "src_ip": src,
    }


def audit(action: str, target: dict | None = None, result: str = "success", **extra) -> None:
    """Emit one audit event.

    ``action`` is a dotted verb such as ``pod.delete`` or ``secret.read``;
    ``target`` is typically ``{"kind", "name", "namespace"}``.
    """
    event = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **_actor(),
        "action": action,
        "target": target or {},
        "result": result,
        **extra,
    }
    _audit.info(json.dumps(event, default=str, sort_keys=True))
