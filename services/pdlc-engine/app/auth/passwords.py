"""Password hashing — bcrypt directly (passlib is unmaintained + breaks on bcrypt 4.x)."""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    # bcrypt hard-caps the input at 72 bytes; truncate explicitly to avoid errors.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("ascii"))
    except Exception:
        return False
