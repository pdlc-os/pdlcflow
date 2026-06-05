"""Phase H bundle 1 — checkpointer + dispatch seam (hermetic parts).

The Postgres/Arq paths require live infra (verified via docker compose); here we
verify the seam: defaults stay in-memory/inline, conn-string conversion is
correct, and a missing Postgres falls back to MemorySaver without crashing.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.runtime import InlineDispatcher, get_dispatcher, wire_dispatcher
from app.runtime.dispatch import ArqDispatcher
from app.runtime.graph_runner import _psycopg_conninfo, build_checkpointer
from langgraph.checkpoint.memory import MemorySaver


def test_conninfo_strips_async_driver():
    assert _psycopg_conninfo("postgresql+asyncpg://u:p@h/db") == "postgresql://u:p@h/db"
    assert _psycopg_conninfo("postgresql+psycopg://u:p@h/db") == "postgresql://u:p@h/db"


def test_checkpointer_defaults_to_memorysaver():
    assert isinstance(build_checkpointer(None), MemorySaver)
    cfg = SimpleNamespace(use_postgres_checkpointer=False, db_url="x")
    assert isinstance(build_checkpointer(cfg), MemorySaver)


def test_checkpointer_falls_back_when_postgres_unreachable():
    # use_postgres_checkpointer set but the DB is unreachable → MemorySaver, no crash.
    cfg = SimpleNamespace(
        use_postgres_checkpointer=True,
        db_url="postgresql+asyncpg://nope:nope@127.0.0.1:1/none",
        pg_pool_max_size=2,
    )
    assert isinstance(build_checkpointer(cfg), MemorySaver)


def test_dispatcher_defaults_inline_and_selects_arq():
    wire_dispatcher(SimpleNamespace(use_arq_dispatch=False))
    assert isinstance(get_dispatcher(), InlineDispatcher)

    wire_dispatcher(SimpleNamespace(use_arq_dispatch=True, redis_url="redis://localhost:6379/0"))
    assert isinstance(get_dispatcher(), ArqDispatcher)

    # restore inline for other tests
    wire_dispatcher(SimpleNamespace(use_arq_dispatch=False))
