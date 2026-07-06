"""Liveness / readiness probes.

`/health` is pure liveness — always 200 while the process runs.

`/health/ready` reports real dependency status (was hardcoded "stub" until the
quick-wins honesty pass):

  db     ok | degraded | unconfigured — SELECT 1 when any Postgres-backed
         feature is on (checkpointer / task store / analytics)
  redis  ok | degraded | unconfigured — PING when any Redis-backed feature is
         on (bus / arq / rate limiting / breaker via failover)
  llm    ok | degraded | unprobed     — the instance-default probe (PRD-03)

Semantics: a **degraded db** flips readiness (503) when Postgres is the
configured store — routing traffic to a pod that can't reach its database
helps no one. Redis and LLM never flip readiness (fail-open philosophy: the
bus/limiter/breaker all degrade gracefully). Checks are cached ~8 s and use
sub-second timeouts so the probe itself stays cheap.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Response

from ..config import settings
from ..llm import probe

router = APIRouter(tags=["health"])

_TTL_S = 8.0
_cache: dict[str, tuple[str, float]] = {}


def reset_health_cache() -> None:
    _cache.clear()


def _cached(name: str, fn) -> str:
    hit = _cache.get(name)
    if hit is not None and hit[1] > time.monotonic():
        return hit[0]
    try:
        status = fn()
    except Exception:  # a probe bug must never take the endpoint down
        status = "degraded"
    _cache[name] = (status, time.monotonic() + _TTL_S)
    return status


def _db_configured() -> bool:
    return (
        getattr(settings, "use_postgres_checkpointer", False)
        or getattr(settings, "task_store", "memory") == "postgres"
        or getattr(settings, "analytics_backend", "memory") == "postgres"
    )


def _redis_configured() -> bool:
    return (
        getattr(settings, "use_redis_bus", False)
        or getattr(settings, "use_arq_dispatch", False)
        or getattr(settings, "rate_limit_enabled", False)
    )


def _check_db() -> str:
    if not _db_configured():
        return "unconfigured"
    from sqlalchemy import text

    from ..db.session import get_sync_engine

    try:
        engine = get_sync_engine(settings)
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return "ok"
    except Exception:
        return "degraded"


def _check_redis() -> str:
    if not _redis_configured():
        return "unconfigured"
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url, socket_timeout=0.25, socket_connect_timeout=0.25)
        client.ping()
        return "ok"
    except Exception:
        return "degraded"


# Injectable for tests (no Postgres/Redis in the hermetic suite).
_db_checker = _check_db
_redis_checker = _check_redis


def set_health_checkers(db=None, redis=None) -> None:
    global _db_checker, _redis_checker
    if db is not None:
        _db_checker = db
    if redis is not None:
        _redis_checker = redis


def reset_health_checkers() -> None:
    global _db_checker, _redis_checker
    _db_checker = _check_db
    _redis_checker = _check_redis
    reset_health_cache()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": "A"}


@router.get("/health/ready")
def ready(response: Response) -> dict:
    checks = {
        "db": _cached("db", _db_checker),
        "redis": _cached("redis", _redis_checker),
        "llm": probe.instance_llm_status(),
    }
    # Only the db can flip readiness — and only when Postgres is configured.
    degraded = checks["db"] == "degraded"
    if degraded:
        response.status_code = 503
    return {"status": "degraded" if degraded else "ready", "checks": checks}
