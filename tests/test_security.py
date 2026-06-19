"""Tests for the security hardening: Secret redaction, WebSocket origin check,
and HTTP security headers."""

from types import SimpleNamespace

from kubernetes import client as k8s

from freelens import config
from freelens.k8s import operations as ops
from freelens.security import _HEADERS, register_security_headers
from freelens.terminal import _origin_allowed


# --------------------------------------------------------------------------- #
# H1 — Secret values must never be rendered in the YAML tab.
# --------------------------------------------------------------------------- #
def test_secret_values_are_redacted_in_yaml():
    secret = k8s.V1Secret(
        metadata=k8s.V1ObjectMeta(name="db", namespace="demo"),
        type="Opaque",
        data={"password": "c3VwZXJzZWNyZXQ=", "token": "YWJj"},
    )
    out = ops.to_yaml(secret)
    # Key names are kept, base64 values are gone.
    assert "password" in out and "token" in out
    assert "c3VwZXJzZWNyZXQ=" not in out
    assert "YWJj" not in out
    assert "<redacted>" in out


def test_non_secret_objects_are_not_redacted():
    cfg = k8s.V1ConfigMap(
        metadata=k8s.V1ObjectMeta(name="cm", namespace="demo"),
        data={"greeting": "hello"},
    )
    out = ops.to_yaml(cfg)
    assert "hello" in out


# --------------------------------------------------------------------------- #
# H3 — /ws/exec must reject cross-origin / origin-less handshakes (CSWSH).
# --------------------------------------------------------------------------- #
def _req(origin, host="localhost:8050"):
    return SimpleNamespace(headers={"Origin": origin} if origin else {}, host=host)


def test_same_origin_is_allowed():
    assert _origin_allowed(_req("http://localhost:8050")) is True


def test_missing_origin_is_rejected():
    assert _origin_allowed(_req(None)) is False


def test_foreign_origin_is_rejected():
    assert _origin_allowed(_req("https://evil.example")) is False


def test_allow_listed_origin_is_accepted(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://lens.hospital.fr"])
    assert _origin_allowed(_req("https://lens.hospital.fr", host="other")) is True


# --------------------------------------------------------------------------- #
# B2 — security headers are set on every response.
# --------------------------------------------------------------------------- #
def test_security_headers_applied():
    from flask import Flask

    app = Flask(__name__)

    @app.route("/")
    def index():
        return "ok"

    register_security_headers(app)
    resp = app.test_client().get("/")
    for name, value in _HEADERS.items():
        assert resp.headers.get(name) == value
