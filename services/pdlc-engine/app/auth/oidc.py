"""Generic OIDC verification for SaaS/SSO deployments (T2-4).

Covers any spec-compliant OIDC provider — AWS Cognito, Google Identity
Platform, Entra/AD B2C, Auth0 — by validating access/ID tokens against the
issuer's JWKS (discovery-resolved, TTL-cached) with issuer + audience checks,
then mapping claims to a PDLC `Identity`. On first login the user's org + role
are provisioned from configurable claims; thereafter the user store is the
source of truth.

Kept off the hot import path — nothing here runs (or requires httpx/network)
unless `auth_mode="oidc"`. Discovery + JWKS + token exchange are the only
network calls; token *verification* is pure once the JWKS is cached.
"""

from __future__ import annotations

import logging
import time

from fastapi import HTTPException, status
from jose import JWTError, jwk, jwt
from jose.utils import base64url_decode  # noqa: F401 - re-exported for tests

from ..config import settings
from .local import Identity

log = logging.getLogger("pdlc.auth.oidc")

# Discovery doc + JWKS caches (issuer-keyed), refreshed on TTL / kid miss.
_discovery_cache: dict[str, tuple[dict, float]] = {}
_jwks_cache: dict[str, tuple[dict, float]] = {}


def reset_caches() -> None:
    _discovery_cache.clear()
    _jwks_cache.clear()


def _http_get(url: str) -> dict:
    import httpx

    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    return resp.json()


def discovery() -> dict:
    """The issuer's OIDC discovery document (`.well-known/openid-configuration`),
    TTL-cached. Raises 503 if the issuer is unreachable."""
    issuer = settings.oidc_issuer.rstrip("/")
    if not issuer:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="oidc_issuer is not configured")
    hit = _discovery_cache.get(issuer)
    if hit and hit[1] > time.monotonic():
        return hit[0]
    try:
        doc = _http_get(f"{issuer}/.well-known/openid-configuration")
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="OIDC issuer discovery failed") from exc
    _discovery_cache[issuer] = (doc, time.monotonic() + settings.oidc_jwks_ttl_s)
    return doc


def _jwks(force: bool = False) -> dict:
    issuer = settings.oidc_issuer.rstrip("/")
    hit = _jwks_cache.get(issuer)
    if hit and not force and hit[1] > time.monotonic():
        return hit[0]
    try:
        keys = _http_get(discovery()["jwks_uri"])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="OIDC JWKS fetch failed") from exc
    _jwks_cache[issuer] = (keys, time.monotonic() + settings.oidc_jwks_ttl_s)
    return keys


def _key_for(kid: str, *, allow_refetch: bool = True) -> dict:
    for key in _jwks().get("keys", []):
        if key.get("kid") == kid:
            return key
    # A rotated key we haven't seen — refetch once before giving up.
    if allow_refetch:
        _jwks(force=True)
        return _key_for(kid, allow_refetch=False)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="unknown signing key")


def verify_token(token: str) -> dict:
    """Validate an OIDC token's signature (via JWKS), issuer, and audience;
    return its claims. Raises 401 on any failure."""
    try:
        headers = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="malformed token") from exc
    key_data = _key_for(headers.get("kid", ""))
    public_key = jwk.construct(key_data, key_data.get("alg", "RS256"))
    try:
        claims = jwt.decode(
            token,
            public_key.to_pem().decode() if hasattr(public_key, "to_pem") else key_data,
            algorithms=[key_data.get("alg", "RS256")],
            audience=settings.oidc_audience or None,
            issuer=settings.oidc_issuer.rstrip("/") or None,
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail=f"token validation failed: {exc}") from exc
    return claims


def identity_from_claims(claims: dict) -> Identity:
    """Map validated claims to a PDLC Identity, provisioning org + user on first
    login. After that the user store is authoritative for org/role."""
    from .store import get_user_store

    email = str(claims.get(settings.oidc_email_claim) or claims.get("email") or "").lower()
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="token missing an email claim")
    store = get_user_store()
    rec = store.get_by_email(email)
    if rec:
        return Identity(user_id=rec["user_id"], email=rec["email"],
                        org_id=rec["org_id"], role=rec["role"])

    # First login — provision. Org from the configured claim (by name), role from
    # the configured claim, defaulting sanely.
    org_name = str(claims.get(settings.oidc_org_claim) or "default") if settings.oidc_org_claim else "default"
    role = _map_role(claims.get(settings.oidc_role_claim)) if settings.oidc_role_claim else "member"
    org_id = _get_or_create_org(store, org_name)
    user_id = store.create_user(org_id=org_id, email=email, pw_hash="", role=role)
    log.info("provisioned OIDC user %s (org %s, role %s)", email, org_id, role)
    return Identity(user_id=user_id, email=email, org_id=org_id, role=role)


def _map_role(raw) -> str:
    """Normalize a role claim (may be a list, e.g. Cognito groups) to a PDLC role."""
    values = raw if isinstance(raw, list) else [raw]
    values = [str(v).lower() for v in values if v]
    for candidate in ("owner", "admin", "member", "viewer"):
        if candidate in values:
            return candidate
    return "member"


def _get_or_create_org(store, name: str) -> str:
    """Idempotent org resolution by name (so the same org claim always maps to
    the same org). Falls back to create when the store can't look up by name."""
    getter = getattr(store, "get_org_by_name", None)
    if getter:
        existing = getter(name)
        if existing:
            return existing
    return store.create_org(name)


def current_identity_oidc(token: str) -> Identity:
    return identity_from_claims(verify_token(token))


# --------------------------------------------------------------------------- #
# Studio-facing: public config + the auth-code (PKCE) token exchange.
# --------------------------------------------------------------------------- #
def public_config() -> dict:
    """What the Studio needs to start an auth-code + PKCE redirect login."""
    doc = discovery()
    return {
        "issuer": settings.oidc_issuer.rstrip("/"),
        "authorization_endpoint": doc.get("authorization_endpoint"),
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scopes": settings.oidc_scopes,
    }


def exchange_code(code: str, code_verifier: str, redirect_uri: str) -> dict:
    """Exchange an auth code (+ PKCE verifier) for tokens at the issuer's token
    endpoint, validate the access token, and return {access_token, identity}."""
    import httpx

    token_endpoint = discovery().get("token_endpoint")
    if not token_endpoint:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="issuer has no token endpoint")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri or settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
        "code_verifier": code_verifier,
    }
    try:
        resp = httpx.post(token_endpoint, data=data, timeout=10.0)
        resp.raise_for_status()
        tokens = resp.json()
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="code exchange failed") from exc
    access_token = tokens.get("access_token") or tokens.get("id_token")
    if not access_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="no token returned")
    identity = current_identity_oidc(access_token)
    return {"access_token": access_token, "identity": identity}
