"""Generic OIDC auth (T2-4) — hermetic.

A locally-generated RSA keypair stands in for the issuer's signing key: we build
a JWKS from the public key and monkeypatch the JWKS/discovery fetch, so the full
validate → provision path runs with zero network. Covers signature/issuer/
audience validation, first-login provisioning, idempotent re-login, role/org
claim mapping, and the tamper/rotation failure modes.
"""

from __future__ import annotations

import base64
import time

import pytest
from app.auth import oidc
from app.auth.store import InMemoryUserStore, reset_user_store, set_user_store
from app.config import settings
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwt

ISSUER = "https://issuer.example.com"
AUDIENCE = "pdlc-client"


def _b64u_uint(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture
def rsa_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    jwk_dict = {"kty": "RSA", "kid": "test-key", "use": "sig", "alg": "RS256",
                "n": _b64u_uint(pub.n), "e": _b64u_uint(pub.e)}
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    return private_pem, jwk_dict


@pytest.fixture(autouse=True)
def _oidc_env(monkeypatch, rsa_key):
    _, jwk_dict = rsa_key
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "oidc_audience", AUDIENCE)
    monkeypatch.setattr(settings, "oidc_email_claim", "email")
    monkeypatch.setattr(settings, "oidc_org_claim", "org")
    monkeypatch.setattr(settings, "oidc_role_claim", "roles")
    oidc.reset_caches()
    monkeypatch.setattr(oidc, "_jwks", lambda force=False: {"keys": [jwk_dict]})
    monkeypatch.setattr(oidc, "discovery", lambda: {
        "jwks_uri": f"{ISSUER}/jwks", "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token"})
    set_user_store(InMemoryUserStore())
    yield
    reset_user_store()
    oidc.reset_caches()


def _token(rsa_key, **claims):
    private_pem, _ = rsa_key
    now = int(time.time())
    payload = {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300,
               "sub": "user-123", **claims}
    return jwt.encode(payload, private_pem, algorithm="RS256",
                      headers={"kid": "test-key"})


def test_valid_token_provisions_org_and_user_on_first_login(rsa_key):
    tok = _token(rsa_key, email="Alice@Acme.com", org="acme", roles=["admin"])
    identity = oidc.current_identity_oidc(tok)
    assert identity.email == "alice@acme.com" and identity.role == "admin"
    assert identity.org_id and identity.user_id

    # Second login reuses the provisioned org + user (idempotent) — same ids,
    # and the store's role wins even if the claim changes.
    tok2 = _token(rsa_key, email="alice@acme.com", org="acme", roles=["viewer"])
    again = oidc.current_identity_oidc(tok2)
    assert again.org_id == identity.org_id and again.user_id == identity.user_id
    assert again.role == "admin"


def test_two_users_same_org_claim_share_one_org(rsa_key):
    a = oidc.current_identity_oidc(_token(rsa_key, email="a@acme.com", org="acme", roles=["member"]))
    b = oidc.current_identity_oidc(_token(rsa_key, email="b@acme.com", org="acme", roles=["member"]))
    assert a.org_id == b.org_id  # get_org_by_name makes provisioning idempotent


def test_wrong_audience_is_rejected(rsa_key):
    private_pem, _ = rsa_key
    now = int(time.time())
    bad = jwt.encode({"iss": ISSUER, "aud": "someone-else", "iat": now, "exp": now + 300,
                      "email": "x@y.com"}, private_pem, algorithm="RS256",
                     headers={"kid": "test-key"})
    with pytest.raises(HTTPException) as exc:
        oidc.verify_token(bad)
    assert exc.value.status_code == 401


def test_wrong_issuer_is_rejected(rsa_key):
    private_pem, _ = rsa_key
    now = int(time.time())
    bad = jwt.encode({"iss": "https://evil.example", "aud": AUDIENCE, "iat": now,
                      "exp": now + 300, "email": "x@y.com"}, private_pem,
                     algorithm="RS256", headers={"kid": "test-key"})
    with pytest.raises(HTTPException) as exc:
        oidc.verify_token(bad)
    assert exc.value.status_code == 401


def test_tampered_signature_is_rejected(rsa_key):
    tok = _token(rsa_key, email="a@b.com")
    tampered = tok[:-4] + ("AAAA" if not tok.endswith("AAAA") else "BBBB")
    with pytest.raises(HTTPException) as exc:
        oidc.verify_token(tampered)
    assert exc.value.status_code == 401


def test_unknown_kid_is_rejected(rsa_key):
    private_pem, _ = rsa_key
    now = int(time.time())
    tok = jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300,
                      "email": "a@b.com"}, private_pem, algorithm="RS256",
                     headers={"kid": "rotated-away"})
    with pytest.raises(HTTPException) as exc:
        oidc.verify_token(tok)
    assert exc.value.status_code == 401


def test_missing_email_claim_is_rejected(rsa_key):
    tok = _token(rsa_key, org="acme")  # no email
    with pytest.raises(HTTPException) as exc:
        oidc.current_identity_oidc(tok)
    assert exc.value.status_code == 401


def test_role_defaults_to_member_without_a_role_claim(rsa_key, monkeypatch):
    monkeypatch.setattr(settings, "oidc_role_claim", "")
    identity = oidc.current_identity_oidc(_token(rsa_key, email="c@acme.com", org="acme"))
    assert identity.role == "member"
