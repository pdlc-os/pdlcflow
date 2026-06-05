"""Dispatch seam — run a graph turn inline (default) or enqueue it to Arq.

Inline keeps the synchronous REST contract: the command/resolve endpoints run
the turn via the GraphRunner and return the resulting pending interaction in
the HTTP response (Studio reads it from there). Arq dispatch (opt-in, set
`use_arq_dispatch`) enqueues a job for the worker process — which shares
Postgres graph state via the PostgresSaver checkpointer — and the pending
interaction is delivered to the client over the Redis-backed WebSocket bus
(Phase H bundle 2). In that mode the HTTP response carries `pending=None`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from .graph_runner import get_runner
from .ports import PendingInteraction

log = logging.getLogger("pdlc.runtime.dispatch")


class Dispatcher(Protocol):
    def start(self, thread_id: str, state: dict) -> PendingInteraction | None: ...
    def resume(self, thread_id: str, resume_value) -> PendingInteraction | None: ...


class InlineDispatcher:
    """Default: run the turn synchronously and return the pending interaction."""

    def start(self, thread_id: str, state: dict) -> PendingInteraction | None:
        return get_runner().start(thread_id, state)

    def resume(self, thread_id: str, resume_value) -> PendingInteraction | None:
        return get_runner().resume(thread_id, resume_value)


class ArqDispatcher:
    """Opt-in: enqueue the turn for the worker. Returns None — the pending
    interaction arrives over the (Redis) bus once the worker runs the turn.

    Uses a short-lived pool per enqueue so the sync route handlers don't have to
    share an event loop with a boot-time Arq pool (avoids cross-loop bugs).
    Enqueues are infrequent relative to the graph work the worker does.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    def _enqueue(self, fn: str, *args) -> None:
        async def _go() -> None:
            from arq import create_pool
            from arq.connections import RedisSettings

            pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
            try:
                await pool.enqueue_job(fn, *args)
            finally:
                await pool.close()

        asyncio.run(_go())

    def start(self, thread_id: str, state: dict) -> PendingInteraction | None:
        self._enqueue("start_graph", thread_id, state)
        return None

    def resume(self, thread_id: str, resume_value) -> PendingInteraction | None:
        self._enqueue("resume_graph", thread_id, resume_value)
        return None


_dispatcher: Dispatcher = InlineDispatcher()


def set_dispatcher(dispatcher: Dispatcher) -> None:
    global _dispatcher
    _dispatcher = dispatcher


def reset_dispatcher() -> None:
    global _dispatcher
    _dispatcher = InlineDispatcher()


def get_dispatcher() -> Dispatcher:
    return _dispatcher


def wire_dispatcher(settings) -> Dispatcher:
    """Boot: select the dispatcher from settings (inline unless use_arq_dispatch)."""
    if getattr(settings, "use_arq_dispatch", False):
        set_dispatcher(ArqDispatcher(settings.redis_url))
        log.info("Arq dispatch active — turns run on the worker")
    else:
        reset_dispatcher()
    return get_dispatcher()
