"""GraphRunner — drives the real meta-graph across interrupt/resume turns.

This is the load-bearing adapter: it compiles `meta_graph` with a checkpointer
so `interrupt()` sites in the nested phase subgraphs (Discover/Define/Design/
Plan gates + Socratic/Bloom's question rounds) become pausable and resumable.

- `start(thread_id, state)`  → invoke to the first pause (or completion).
- `resume(thread_id, value)` → Command(resume=value) to the next pause.

After every turn it reconciles the graph's pending `interrupt()` (if any) into
the GateStore and publishes a frame on the thread's EventBus channel. One
runner instance owns one checkpointer, so start and resume must share it — the
module-level singleton (`get_runner`) guarantees that within a process.

Checkpointer seam: MemorySaver by default (in-process; fine while the API
drives turns inline). Production injects a PostgresSaver so Arq workers in
other processes resume the same thread; see `build_checkpointer`.
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.graphs.meta import build_meta_graph

from .ports import (
    PendingInteraction,
    get_event_bus,
    get_gate_store,
)

log = logging.getLogger("pdlc.runtime")


def _psycopg_conninfo(db_url: str) -> str:
    """Convert a SQLAlchemy URL (postgresql+asyncpg://…) to a psycopg conninfo
    (postgresql://…) for the PostgresSaver connection pool."""
    return db_url.replace("+asyncpg", "").replace("+psycopg", "")


def build_checkpointer(settings=None):
    """Return a checkpointer.

    With `use_postgres_checkpointer`, a pooled `PostgresSaver` so graph state is
    durable and shared across the API + Arq worker processes; otherwise a
    `MemorySaver` (dev/test and single-process runs). Any failure to reach
    Postgres falls back to MemorySaver so the engine still boots.
    """
    if settings is not None and getattr(settings, "use_postgres_checkpointer", False):
        try:  # prod-only path — requires a reachable Postgres (verified via docker compose)
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                conninfo=_psycopg_conninfo(settings.db_url),
                max_size=getattr(settings, "pg_pool_max_size", 20),
                open=True,
                kwargs={"autocommit": True, "row_factory": dict_row},
            )
            saver = PostgresSaver(pool)
            saver.setup()  # idempotent — creates the langgraph checkpoint tables
            log.info("PostgresSaver checkpointer active (durable, multi-process)")
            return saver
        except Exception as exc:  # pragma: no cover - prod-only path
            log.warning("PostgresSaver unavailable (%s); falling back to MemorySaver", exc)
    return MemorySaver()


def _channel(thread_id: str) -> str:
    return f"thread:{thread_id}"


class GraphRunner:
    def __init__(self, checkpointer=None) -> None:
        self._graph = build_meta_graph(checkpointer=checkpointer or MemorySaver())

    # -- public API ---------------------------------------------------------
    def start(self, thread_id: str, state: dict) -> PendingInteraction | None:
        return self._advance(thread_id, state)

    def resume(self, thread_id: str, resume_value) -> PendingInteraction | None:
        return self._advance(thread_id, Command(resume=resume_value))

    def snapshot(self, thread_id: str) -> dict:
        cfg = {"configurable": {"thread_id": thread_id}}
        return dict(self._graph.get_state(cfg).values)

    # -- internals ----------------------------------------------------------
    def _advance(self, thread_id: str, invoke_input) -> PendingInteraction | None:
        cfg = {"configurable": {"thread_id": thread_id}}
        self._graph.invoke(invoke_input, cfg)
        return self._sync_pending(thread_id, cfg)

    def _pending_interrupt(self, cfg) -> dict | None:
        state = self._graph.get_state(cfg)
        for task in state.tasks:
            if task.interrupts:
                return task.interrupts[0].value
        return None

    def _sync_pending(self, thread_id: str, cfg) -> PendingInteraction | None:
        bus = get_event_bus()
        store = get_gate_store()
        intr = self._pending_interrupt(cfg)

        if intr is None:
            # Thread reached a terminal state for this turn.
            store.close_open_for_thread(thread_id)
            values = self._graph.get_state(cfg).values
            summary = {
                k: values.get(k)
                for k in (
                    "phase", "night_shift_outcome", "night_shift_abort_reason",
                    "night_shift_run_id", "version", "deploy_tier", "deploy_url",
                    "operation_complete",
                )
                if values.get(k) is not None
            }
            bus.publish(
                _channel(thread_id),
                {"type": "thread.completed", "thread_id": thread_id, "summary": summary},
            )
            return None

        values = self._graph.get_state(cfg).values
        kind = intr.get("kind", "user_input_required")
        rec = store.open(
            PendingInteraction(
                thread_id=thread_id,
                org_id=str(values.get("org_id", "")),
                project_id=str(values.get("project_id", "")),
                kind=kind,
                gate_kind=intr.get("gate"),
                payload=intr,
            )
        )
        bus.publish(
            _channel(thread_id),
            {"type": "interaction.opened", "interaction": rec.as_dict()},
        )
        return rec


# --------------------------------------------------------------------------- #
# Module-level singleton
# --------------------------------------------------------------------------- #
_runner: GraphRunner | None = None


def set_runner(runner: GraphRunner) -> None:
    global _runner
    _runner = runner


def get_runner() -> GraphRunner:
    global _runner
    if _runner is None:
        _runner = GraphRunner()
    return _runner


def reset_runner() -> None:
    """Tests: fresh runner (fresh MemorySaver) so thread ids don't collide."""
    global _runner
    _runner = GraphRunner()
