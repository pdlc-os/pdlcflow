"""Redis-backed event bus — cross-process WebSocket fan-out (Phase H bundle 2).

`publish` is synchronous (called from graph nodes / sync routes, in the API or
the Arq worker): each frame is appended to a capped per-channel Redis list (for
reconnect replay) and PUBLISHed on the channel (for live delivery). `listen`
(async, used by the WS handler) replays the bounded history then subscribes to
the pub/sub channel — so a frame published by the worker reaches a WebSocket
held open by the API.

Verified via docker-compose (no Redis in CI); the in-memory bus remains the
default and the test path.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("pdlc.runtime.redis_bus")


def _frames_key(channel: str) -> str:
    return f"{channel}:frames"


class RedisEventBus:
    def __init__(self, redis_url: str, *, replay: int = 200, ttl_s: int = 86_400) -> None:
        import redis  # sync client for publish/history

        self._url = redis_url
        self._replay = replay
        self._ttl_s = ttl_s
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def publish(self, channel: str, frame: dict) -> None:
        data = json.dumps(frame)
        key = _frames_key(channel)
        try:
            pipe = self._client.pipeline()
            pipe.rpush(key, data)
            pipe.ltrim(key, -self._replay, -1)
            pipe.expire(key, self._ttl_s)
            pipe.publish(channel, data)
            pipe.execute()
        except Exception as exc:  # never raise on telemetry/fan-out
            log.warning("redis publish failed on %s: %s", channel, exc)

    def history(self, channel: str) -> list[dict]:
        try:
            return [json.loads(x) for x in self._client.lrange(_frames_key(channel), 0, -1)]
        except Exception as exc:
            log.warning("redis history failed on %s: %s", channel, exc)
            return []

    async def listen(self, channel: str):
        """Replay the bounded history, then stream live frames from pub/sub."""
        import redis.asyncio as aredis

        client = aredis.from_url(self._url, decode_responses=True)
        # Replay first so a client attaching mid-run sees the open gate.
        try:
            for raw in await client.lrange(_frames_key(channel), 0, -1):
                yield json.loads(raw)
        except Exception as exc:  # pragma: no cover - prod-only path
            log.warning("redis replay failed on %s: %s", channel, exc)

        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await client.aclose()


def wire_event_bus(settings):
    """Boot: select the event bus from settings (in-memory unless use_redis_bus)."""
    from .ports import set_event_bus

    if getattr(settings, "use_redis_bus", False):
        set_event_bus(RedisEventBus(settings.redis_url))
        log.info("Redis event bus active — cross-process WebSocket fan-out")
    return None
