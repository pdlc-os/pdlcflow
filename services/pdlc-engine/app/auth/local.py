"""Local JWT auth for self-host single-tenant deployments."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from ..config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token", auto_error=False)


class Identity(BaseModel):
    user_id: str
    email: str
    org_id: str
    role: str


def issue_token(identity: Identity) -> str:
    now = datetime.now(UTC)
    claims = {
        **identity.model_dump(),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_ttl_s)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_alg)


def _decode(token: str) -> Identity:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    return Identity(**{k: claims[k] for k in ("user_id", "email", "org_id", "role")})


def current_identity(token: Annotated[str | None, Depends(oauth2_scheme)]) -> Identity:
    """Strict — always requires a valid token (used by /v1/auth/me + user mgmt)."""
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing token")
    return _decode(token)


def get_principal(token: Annotated[str | None, Depends(oauth2_scheme)]) -> Identity | None:
    """Flag-aware principal: None when auth is off (open API); a validated
    Identity when `auth_required` is on (401 if the token is missing/invalid)."""
    if not settings.auth_required:
        return None
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing token")
    return _decode(token)


def require_admin(principal: Annotated[Identity | None, Depends(get_principal)]) -> Identity | None:
    """Router-level guard: when auth is on, require the admin/owner role; no-op when off."""
    if principal is not None and principal.role not in ("admin", "owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin role required")
    return principal


def authenticate(email: str, password: str) -> Identity | None:
    """Verify credentials against the user store; returns an Identity or None."""
    from .passwords import verify_password
    from .store import get_user_store

    rec = get_user_store().get_by_email(email)
    if not rec or not verify_password(password, rec.get("pw_hash", "")):
        return None
    return Identity(user_id=rec["user_id"], email=rec["email"], org_id=rec["org_id"], role=rec["role"])


def resolve_org(principal: Identity | None, requested: str | None, label: str, *, admin: bool = False) -> str:
    """Resolve the effective org for a request, enforcing tenant + role rules.

    auth off  → behaves like the cross-org ban: `requested` is required (else 403).
    auth on   → org comes from the token; a mismatched `requested` is rejected;
                `admin=True` routes require the admin/owner role.
    """
    if principal is None:
        if not requested:
            _audit_denied(label)
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail="org_id required — cross-org analytics are not permitted")
        return requested
    if admin and principal.role not in ("admin", "owner"):
        _audit_denied(label)
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin role required")
    if requested and requested != principal.org_id:
        _audit_denied(label)
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="cross-org access is not permitted")
    return principal.org_id


def _audit_denied(label: str) -> None:
    try:
        from uuid import UUID

        from event_schema import EventEnvelope

        from ..clickstream import get_emitter

        get_emitter().emit_envelope(EventEnvelope(
            event_type="admin.access.denied", org_id=UUID(int=0), project_id=UUID(int=0),
            payload={"path": label, "reason": "auth/cross-org denied"}))
    except Exception:
        pass
