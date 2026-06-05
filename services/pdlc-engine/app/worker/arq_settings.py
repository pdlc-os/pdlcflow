"""Arq worker — runs graph turns enqueued by the engine.

`uv run arq app.worker.arq_settings.WorkerSettings` boots a worker process
that picks up `start_graph` jobs and drives the meta-graph forward.
"""

from __future__ import annotations

from ..clickstream import wire_emitter
from ..config import settings


async def start_graph(ctx: dict, thread_id: str, command: str) -> dict:
    """Phase A stub. Real impl: load checkpointed state, route by command,
    invoke meta_graph with stream config, push tokens to Redis Pub/Sub.
    """
    return {"thread_id": thread_id, "command": command, "status": "stubbed"}


async def startup(_ctx: dict) -> None:
    wire_emitter(settings)


async def shutdown(_ctx: dict) -> None:
    return None


class WorkerSettings:
    functions = [start_graph]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = None  # set from settings.redis_url at boot in Phase B
