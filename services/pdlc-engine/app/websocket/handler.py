"""WebSocket — per-thread fan-out from the EventBus.

On connect the handler sends a hello, then streams frames from
`bus.listen(channel)` — an async iterator that replays the thread's recent
history (so a client attaching after a gate opened still sees it) and then
yields live frames. This is transport-agnostic: the in-memory bus polls its
history; the Redis bus replays a bounded list then subscribes to pub/sub, so a
frame published by the Arq worker reaches a socket held open by the API.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..runtime import get_event_bus

ws_router = APIRouter()


def _authorize(thread_id: str, token: str | None) -> bool:
    """When auth is enforced, the `?token=` JWT must be valid and its org must
    match the thread's org prefix (thread_id = org:project:session). Open otherwise."""
    if not settings.auth_required:
        return True
    if not token:
        return False
    try:
        from ..auth.local import _decode

        identity = _decode(token)
    except Exception:
        return False
    return thread_id.split(":", 1)[0] == identity.org_id


@ws_router.websocket("/ws/threads/{thread_id}")
async def thread_socket(socket: WebSocket, thread_id: str, token: str | None = None) -> None:
    if not _authorize(thread_id, token):
        await socket.close(code=4401)  # policy violation / unauthorized
        return
    await socket.accept()
    bus = get_event_bus()
    channel = f"thread:{thread_id}"

    await socket.send_json({"type": "hello", "thread_id": thread_id})

    # Drain client messages concurrently so a disconnect cancels the pump.
    async def _drain_client() -> None:
        with contextlib.suppress(Exception):
            while True:
                await socket.receive_text()

    drain = asyncio.create_task(_drain_client())
    try:
        async for frame in bus.listen(channel):
            await socket.send_json(frame)
    except WebSocketDisconnect:
        return
    finally:
        drain.cancel()
        with contextlib.suppress(Exception):
            await drain
