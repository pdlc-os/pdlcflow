"""Row-level security middleware — sets app.org_id at the connection layer.

FastAPI middleware reads the JWT claim and binds it; background workers do
the same when picking up an Arq job. Postgres RLS policies (defined in the
Alembic migration) then enforce tenant isolation at the wire — no application
code can leak cross-tenant data because the query won't see other rows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def with_org_scope(session: AsyncSession, org_id: UUID) -> AsyncIterator[None]:
    """Bind app.org_id on the current connection for the duration of the block."""
    await session.execute(text("select set_config('app.org_id', :v, true)"), {"v": str(org_id)})
    yield


def set_org_context(conn, org_id: str) -> None:
    """Sync equivalent — bind app.org_id on a sync connection inside a
    transaction so the RLS policies admit this org's rows. Called by the sync
    Postgres adapters (task store, analytics) at the start of each `begin()`.

    Uses `set_config(..., is_local => true)` rather than `SET LOCAL …` because
    Postgres `SET` does not accept bind parameters.
    """
    conn.execute(text("select set_config('app.org_id', :v, true)"), {"v": str(org_id)})
