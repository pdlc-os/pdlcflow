"""Auth routes — login, whoami, and admin user management (local mode)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth.local import Identity, authenticate, current_identity, issue_token
from ..auth.passwords import hash_password
from ..auth.store import get_user_store
from ..config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    identity: Identity


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    identity = authenticate(req.email, req.password)
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return TokenResponse(access_token=issue_token(identity), identity=identity)


@router.get("/mode")
def auth_mode() -> dict:
    """Which auth mode the Studio should render — password form or SSO redirect."""
    return {"mode": settings.auth_mode, "auth_required": settings.auth_required}


@router.get("/oidc/config")
def oidc_config() -> dict:
    """Public OIDC params the Studio needs to start an auth-code + PKCE login."""
    if settings.auth_mode != "oidc":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="OIDC is not enabled")
    from ..auth.oidc import public_config

    return public_config()


class OIDCExchangeRequest(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str | None = None


@router.post("/oidc/exchange", response_model=TokenResponse)
def oidc_exchange(req: OIDCExchangeRequest) -> TokenResponse:
    """Exchange an auth code (+ PKCE verifier) for a validated session token."""
    if settings.auth_mode != "oidc":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="OIDC is not enabled")
    from ..auth.oidc import exchange_code

    result = exchange_code(req.code, req.code_verifier, req.redirect_uri or "")
    return TokenResponse(access_token=result["access_token"], identity=result["identity"])


@router.get("/me", response_model=Identity)
def me(identity: Identity = Depends(current_identity)) -> Identity:
    return identity


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str = "member"


@router.post("/users", response_model=Identity, status_code=status.HTTP_201_CREATED)
def create_user(req: CreateUserRequest, caller: Identity = Depends(current_identity)) -> Identity:
    # Admins create users within their own org only.
    if caller.role not in ("admin", "owner"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="admin role required")
    if req.role not in ("owner", "admin", "member", "viewer"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid role")
    store = get_user_store()
    if store.get_by_email(req.email):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="user already exists")
    user_id = store.create_user(
        org_id=caller.org_id, email=req.email, pw_hash=hash_password(req.password), role=req.role
    )
    return Identity(user_id=user_id, email=req.email.lower(), org_id=caller.org_id, role=req.role)
