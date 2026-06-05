"""WebSocket — per-thread fan-out from Redis Pub/Sub.

The handler subscribes to `thread:{id}` on Redis Pub/Sub (and, depending on
the client's filter expression, to `org:{id}:status`, `org:{id}:project:{p}:
night-shift`, etc.) and forwards each frame to the connected Studio client.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()


@ws_router.websocket("/ws/threads/{thread_id}")
async def thread_socket(socket: WebSocket, thread_id: str) -> None:
    await socket.accept()
    try:
        # Phase A: echo until the client disconnects so dev environments can
        # exercise the connect path. Phase B wires the Redis subscriber.
        await socket.send_json({"type": "hello", "thread_id": thread_id, "phase": "A"})
        while True:
            msg = await socket.receive_text()
            await socket.send_json({"type": "echo", "msg": msg})
    except WebSocketDisconnect:
        return
