"""Sync SQLAlchemy engine for the Postgres-backed adapters.

The task store and analytics store are called from synchronous contexts (graph
nodes via the runner thread; the emitter drain thread; sync admin handlers), so
a sync `psycopg` engine is the right fit. The URL is derived from the
SQLAlchemy `+asyncpg` setting by swapping the driver to `+psycopg`.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine

_engine: Engine | None = None


def _sync_url(db_url: str) -> str:
    if "+asyncpg" in db_url:
        return db_url.replace("+asyncpg", "+psycopg")
    if "+psycopg" in db_url or db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+psycopg://")
    return db_url


def get_sync_engine(settings) -> Engine:
    """Lazily build + cache one pooled sync engine for the process."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _sync_url(settings.db_url),
            pool_pre_ping=True,
            pool_size=getattr(settings, "pg_pool_max_size", 20),
            future=True,
        )
    return _engine


def reset_sync_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
