"""Local JWT auth for self-host single-tenant deployments."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    now = datetime.now(timezone.utc)
    claims = {
        **identity.model_dump(),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_ttl_s)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_alg)


def current_identity(token: Annotated[str | None, Depends(oauth2_scheme)]) -> Identity:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing token")
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    return Identity(**{k: claims[k] for k in ("user_id", "email", "org_id", "role")})
