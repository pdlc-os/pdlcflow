"""Phase 1 auth — enforcement is flag-gated; org is derived from the token."""

from __future__ import annotations

from uuid import uuid4

from app.auth.passwords import hash_password, verify_password
from app.auth.store import get_user_store
from app.config import settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _seed_user(email="admin@acme.test", password="pw-12345", role="admin"):
    store = get_user_store()
    org_id = store.create_org("acme")
    store.create_user(org_id=org_id, email=email, pw_hash=hash_password(password), role=role)
    return org_id


def test_password_hash_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret" and verify_password("s3cret", h) and not verify_password("nope", h)


# ---- auth OFF (default): open API, unchanged behavior ----

def test_auth_off_commands_open():
    r = client.post("/v1/commands", json={
        "command": "doctor", "org_id": str(uuid4()), "project_id": str(uuid4())})
    assert r.status_code == 200


# ---- auth ON ----

def test_login_issues_token_and_protects_commands():
    settings.auth_required = True
    org_id = _seed_user()

    # no token -> 401
    assert client.post("/v1/commands", json={
        "command": "doctor", "project_id": str(uuid4())}).status_code == 401

    # login -> token
    r = client.post("/v1/auth/login", json={"email": "admin@acme.test", "password": "pw-12345"})
    assert r.status_code == 200
    body = r.json()
    assert body["identity"]["org_id"] == org_id and body["identity"]["role"] == "admin"
    token = body["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # authed command works; org is derived from the token (none sent in body)
    ok = client.post("/v1/commands", json={"command": "doctor", "project_id": str(uuid4())}, headers=h)
    assert ok.status_code == 200
    assert ok.json()["thread_id"].split(":", 1)[0] == org_id


def test_bad_credentials_rejected():
    settings.auth_required = True
    _seed_user()
    assert client.post("/v1/auth/login",
                       json={"email": "admin@acme.test", "password": "wrong"}).status_code == 401


def test_cross_org_request_is_rejected():
    settings.auth_required = True
    _seed_user()
    token = client.post("/v1/auth/login",
                        json={"email": "admin@acme.test", "password": "pw-12345"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    # passing a DIFFERENT org_id than the token's -> 403
    r = client.post("/v1/commands",
                    json={"command": "doctor", "org_id": str(uuid4()), "project_id": str(uuid4())}, headers=h)
    assert r.status_code == 403


def test_admin_routes_require_token_and_admin_role():
    settings.auth_required = True
    _seed_user(email="member@acme.test", role="member")
    # no token -> 401
    assert client.get("/v1/admin/live").status_code == 401
    token = client.post("/v1/auth/login",
                        json={"email": "member@acme.test", "password": "pw-12345"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    # member role -> 403 on admin route
    assert client.get("/v1/admin/live", headers=h).status_code == 403


def test_admin_route_works_for_admin_and_scopes_to_token_org():
    settings.auth_required = True
    _seed_user()
    token = client.post("/v1/auth/login",
                        json={"email": "admin@acme.test", "password": "pw-12345"}).json()["access_token"]
    r = client.get("/v1/admin/live", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and "events" in r.json()


def test_me_endpoint_requires_token():
    settings.auth_required = True
    _seed_user()
    assert client.get("/v1/auth/me").status_code == 401
    token = client.post("/v1/auth/login",
                        json={"email": "admin@acme.test", "password": "pw-12345"}).json()["access_token"]
    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "admin@acme.test"


def test_bootstrap_creates_admin_when_configured():
    from app.auth.wiring import wire_auth

    settings.bootstrap_admin_email = "boot@acme.test"
    settings.bootstrap_admin_password = "boot-pw-123"
    try:
        wire_auth(settings)  # task_store=memory -> in-memory store + bootstrap
        rec = get_user_store().get_by_email("boot@acme.test")
        assert rec and rec["role"] == "admin"
    finally:
        settings.bootstrap_admin_email = None
        settings.bootstrap_admin_password = None
