"""WebSocket — per-thread fan-out from the EventBus.

On connect the handler replays the thread's frame history (so a client that
attaches after a gate opened still sees it), then streams new frames as the
GraphRunner publishes them. The in-memory bus is polled by cursor (robust
whether frames are published from the request threadpool or a worker); the
production Redis adapter swaps polling for a real subscription.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..runtime import get_event_bus

ws_router = APIRouter()

_POLL_INTERVAL_S = 0.1


@ws_router.websocket("/ws/threads/{thread_id}")
async def thread_socket(socket: WebSocket, thread_id: str) -> None:
    await socket.accept()
    bus = get_event_bus()
    channel = f"thread:{thread_id}"

    await socket.send_json({"type": "hello", "thread_id": thread_id})

    cursor = 0
    try:
        while True:
            frames = bus.history(channel)
            while cursor < len(frames):
                await socket.send_json(frames[cursor])
                cursor += 1
            # Interleave client liveness without blocking the frame pump.
            try:
                await asyncio.wait_for(socket.receive_text(), timeout=_POLL_INTERVAL_S)
            except TimeoutError:
                pass
    except WebSocketDisconnect:
        return
