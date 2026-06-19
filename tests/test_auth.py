"""Tests for the authentication guard, identity propagation, CSRF and
per-user Kubernetes impersonation."""

import pytest
from flask import Flask, g

from freelens import auth, config
from freelens.k8s import client as k8s_client


@pytest.fixture(autouse=True)
def _reset_config(monkeypatch):
    # Each test sets its own auth mode; default to a clean proxy config.
    monkeypatch.setattr(config, "AUTH_MODE", "proxy")
    monkeypatch.setattr(config, "TRUSTED_PROXIES", ["127.0.0.1"])
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", [])
    monkeypatch.setattr(config, "IMPERSONATE", True)


def _app():
    app = Flask(__name__)
    auth.register_auth(app)

    @app.route("/r/pods")
    def pods():
        return {"user": auth.current_identity().user}

    @app.route("/act", methods=["POST"])
    def act():
        return {"ok": True}

    return app


# --------------------------------------------------------------------------- #
# identity_from_request
# --------------------------------------------------------------------------- #
def test_proxy_identity_from_trusted_proxy():
    app = _app()
    with app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Auth-Request-User": "alice",
                 "X-Auth-Request-Email": "alice@chu.fr",
                 "X-Auth-Request-Groups": "cardio,admins"},
    ):
        ident = auth.identity_from_request()
    assert ident.user == "alice"
    assert ident.email == "alice@chu.fr"
    assert ident.groups == ("cardio", "admins")


def test_headers_from_untrusted_source_are_ignored(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", ["10.0.0.0/8"])
    app = _app()
    with app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "127.0.0.1"},
        headers={"X-Auth-Request-User": "attacker"},
    ):
        assert auth.identity_from_request() is None


def test_disabled_mode_yields_local_identity(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "disabled")
    app = _app()
    with app.test_request_context("/"):
        ident = auth.identity_from_request()
    assert ident.is_local


# --------------------------------------------------------------------------- #
# before_request guard + CSRF
# --------------------------------------------------------------------------- #
def test_unauthenticated_request_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXIES", [])  # nothing trusted
    client = _app().test_client()
    assert client.get("/r/pods").status_code == 401


def test_authenticated_request_passes():
    client = _app().test_client()
    resp = client.get("/r/pods", headers={"X-Auth-Request-User": "bob"})
    assert resp.status_code == 200
    assert resp.get_json()["user"] == "bob"


def test_healthz_is_public():
    assert _app().test_client().get("/healthz").status_code == 200


def test_cross_origin_post_is_blocked():
    client = _app().test_client()
    resp = client.post("/act", headers={"X-Auth-Request-User": "bob",
                                        "Origin": "https://evil.example"})
    assert resp.status_code == 403


def test_same_origin_post_is_allowed():
    client = _app().test_client()
    resp = client.post("/act", base_url="http://localhost",
                       headers={"X-Auth-Request-User": "bob",
                                "Origin": "http://localhost"})
    assert resp.status_code == 200


def test_post_without_origin_is_blocked():
    client = _app().test_client()
    resp = client.post("/act", headers={"X-Auth-Request-User": "bob"})
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Impersonation
# --------------------------------------------------------------------------- #
def test_get_user_clients_sets_impersonation_headers(monkeypatch):
    monkeypatch.setattr(k8s_client, "_load_config", lambda: None)
    k8s_client.get_user_clients.cache_clear()
    clients = k8s_client.get_user_clients("alice", ("cardio", "admins"))
    headers = clients.core.api_client.default_headers
    assert headers["Impersonate-User"] == "alice"
    assert headers["Impersonate-Group"] == ["cardio", "admins"]


# --------------------------------------------------------------------------- #
# Guardrail: never serve unauthenticated on a network address.
# --------------------------------------------------------------------------- #
def test_guardrail_blocks_disabled_on_non_loopback(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "disabled")
    monkeypatch.setattr(config, "ALLOW_INSECURE", False)
    with pytest.raises(SystemExit):
        auth.enforce_safe_bind("0.0.0.0")


def test_guardrail_allows_disabled_on_loopback(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "disabled")
    monkeypatch.setattr(config, "ALLOW_INSECURE", False)
    auth.enforce_safe_bind("127.0.0.1")  # no raise


def test_guardrail_escape_hatch(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "disabled")
    monkeypatch.setattr(config, "ALLOW_INSECURE", True)
    auth.enforce_safe_bind("0.0.0.0")  # no raise


def test_guardrail_ignores_proxy_mode(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "proxy")
    auth.enforce_safe_bind("0.0.0.0")  # no raise


def test_active_clients_uses_shared_for_local(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(config, "AUTH_MODE", "disabled")
    monkeypatch.setattr(k8s_client, "get_clients", lambda: sentinel)
    app = _app()
    with app.test_request_context("/"):
        g.identity = auth.Identity(user="local-dev")
        assert auth.active_clients() is sentinel
