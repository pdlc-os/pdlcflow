"""Arq worker — runs graph turns enqueued by the engine.

`uv run arq app.worker.arq_settings.WorkerSettings` boots a worker that picks
up `start_graph` / `resume_graph` jobs and drives the meta-graph through the
same GraphRunner the API uses. For cross-process resume the worker must run
with `use_postgres_checkpointer` so it shares thread state with the API; with
the default MemorySaver each process has its own state (single-process dev
runs the turns inline in the API instead).
"""

from __future__ import annotations

from typing import ClassVar

from arq.connections import RedisSettings

from ..clickstream import wire_emitter
from ..config import settings
from ..evals import wire_evals
from ..persistence import wire_persistence
from ..runtime import (
    GraphRunner,
    build_checkpointer,
    get_runner,
    set_runner,
    wire_event_bus,
    wire_llm_backend,
    wire_token_streaming,
)


async def start_graph(ctx: dict, thread_id: str, state: dict) -> dict:
    """Invoke the meta-graph to its first pause for `thread_id`."""
    pending = get_runner().start(thread_id, state)
    return {"thread_id": thread_id, "pending": pending.as_dict() if pending else None}


async def resume_graph(ctx: dict, thread_id: str, resume_value: dict) -> dict:
    """Resume a parked thread with the human's verdict / answers."""
    pending = get_runner().resume(thread_id, resume_value)
    return {"thread_id": thread_id, "pending": pending.as_dict() if pending else None}


async def startup(_ctx: dict) -> None:
    # Bus first so the worker publishes pending + night-shift frames to Redis,
    # where the API's WebSocket subscribers pick them up cross-process.
    wire_event_bus(settings)
    wire_persistence(settings)
    wire_emitter(settings)
    set_runner(GraphRunner(checkpointer=build_checkpointer(settings)))
    wire_llm_backend(settings)
    wire_token_streaming(settings)
    wire_evals(settings)


async def shutdown(_ctx: dict) -> None:
    return None


class WorkerSettings:
    functions: ClassVar = [start_graph, resume_graph]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
