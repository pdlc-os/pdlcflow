"""User store — accounts + org membership for local auth.

In-memory by default (hermetic tests / single-process dev); a Postgres-backed
store (organizations / users / org_members tables) is injected at boot when a
database is configured. Mirrors the other injectable ports.
"""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4


class UserRecord(dict):
    """{user_id, email, org_id, role, pw_hash}."""


class UserStore(Protocol):
    def count_users(self) -> int: ...
    def get_by_email(self, email: str) -> UserRecord | None: ...
    def create_org(self, name: str) -> str: ...
    def create_user(self, *, org_id: str, email: str, pw_hash: str, role: str) -> str: ...


class InMemoryUserStore:
    def __init__(self) -> None:
        self._users: dict[str, UserRecord] = {}  # email -> record
        self._orgs: dict[str, str] = {}  # org_id -> name

    def count_users(self) -> int:
        return len(self._users)

    def get_by_email(self, email: str) -> UserRecord | None:
        return self._users.get(email.lower())

    def create_org(self, name: str) -> str:
        org_id = str(uuid4())
        self._orgs[org_id] = name
        return org_id

    def create_user(self, *, org_id: str, email: str, pw_hash: str, role: str) -> str:
        key = email.lower()
        if key in self._users:
            raise ValueError(f"user already exists: {email}")
        user_id = str(uuid4())
        self._users[key] = UserRecord(
            user_id=user_id, email=key, org_id=org_id, role=role, pw_hash=pw_hash
        )
        return user_id


class PostgresUserStore:
    """Accounts over the organizations / users / org_members tables."""

    def __init__(self, settings) -> None:
        from ..db.session import get_sync_engine

        self._engine = get_sync_engine(settings)

    def count_users(self) -> int:
        from sqlalchemy import func, select

        from ..db.models import User

        with self._engine.begin() as conn:
            return int(conn.execute(select(func.count()).select_from(User)).scalar() or 0)

    def get_by_email(self, email: str) -> UserRecord | None:
        from sqlalchemy import select

        from ..db.models import OrgMember, User

        with self._engine.begin() as conn:
            row = conn.execute(
                select(User.id, User.email, User.password_hash, OrgMember.org_id, OrgMember.role)
                .join(OrgMember, OrgMember.user_id == User.id)
                .where(User.email == email.lower())
                .limit(1)
            ).first()
        if row is None:
            return None
        return UserRecord(
            user_id=str(row.id), email=row.email, org_id=str(row.org_id),
            role=row.role, pw_hash=row.password_hash or "",
        )

    def create_org(self, name: str) -> str:
        from sqlalchemy import insert

        from ..db.models import Organization

        org_id = uuid4()
        with self._engine.begin() as conn:
            conn.execute(insert(Organization).values(
                id=org_id, name=name, slug=f"{name}-{org_id.hex[:8]}".lower(), settings={}))
        return str(org_id)

    def create_user(self, *, org_id: str, email: str, pw_hash: str, role: str) -> str:
        from sqlalchemy import insert

        from ..db.models import OrgMember, User

        user_id = uuid4()
        with self._engine.begin() as conn:
            conn.execute(insert(User).values(id=user_id, email=email.lower(), password_hash=pw_hash))
            conn.execute(insert(OrgMember).values(org_id=org_id, user_id=user_id, role=role))
        return str(user_id)


_store: UserStore = InMemoryUserStore()


def set_user_store(store: UserStore) -> None:
    global _store
    _store = store


def get_user_store() -> UserStore:
    return _store


def reset_user_store() -> None:
    global _store
    _store = InMemoryUserStore()
