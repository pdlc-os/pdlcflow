"""Per-tenant fixed-window RPM limiter (Redis).

Key: `llm:{org_id}:{provider}:{tier}:rpm:{epoch_minute}` — INCR + EXPIRE 60,
compared against the org's RPM. Fixed-window (not sliding) is deliberate: one
round-trip on the hot path, and burst-at-the-boundary error is acceptable for
a quota knob. Acquire happens once per ATTEMPT (each failover attempt is a
real upstream call, so it must count against the quota).

Disabled unless PDLC_RATE_LIMIT_ENABLED. The effective RPM is the org's
`org_quotas.rpm_limit` override (Nexus → Pricing & budget) when set, else the
global `PDLC_LLM_RPM_DEFAULT` (T3-5). Overrides are resolved from the DB with a
short TTL cache so the hot path adds no per-call query. FAIL-OPEN on Redis
errors (a broken limiter must not become the outage).
"""

from __future__ import annotations

import logging
import time

from ..config import settings

log = logging.getLogger("pdlc.llm.ratelimit")

# Per-org RPM overrides, cached briefly (the limiter is on the completion hot
# path). {org_id: (rpm|None, expires)}.
_QUOTA_CACHE: dict[str, tuple[int | None, float]] = {}
_QUOTA_TTL_S = 60.0


def invalidate_quota_cache(org_id: str | None = None) -> None:
    if org_id is None:
        _QUOTA_CACHE.clear()
    else:
        _QUOTA_CACHE.pop(org_id, None)


class RateLimited(RuntimeError):
    """The org exceeded its RPM quota; retry next minute (no failover — this
    is our own quota, not a provider incident)."""

    def __init__(self, org_id: str, provider: str, tier: str, rpm: int) -> None:
        super().__init__(
            f"LLM rate limit reached ({rpm} calls/min for this org) — "
            f"retry shortly [provider={provider}, tier={tier}]"
        )
        self.org_id, self.provider, self.tier, self.rpm = org_id, provider, tier, rpm


class RateLimit:
    def __init__(self, redis_client=None, rpm: int | None = None):
        self._client = redis_client
        # An explicitly-passed rpm is a HARD override (tests / forced config):
        # no per-org DB lookup. Otherwise the effective rpm is resolved per org.
        self._forced_rpm = rpm
        self._rpm = rpm if rpm is not None else getattr(settings, "llm_rpm_default", 60)

    @property
    def rpm(self) -> int:
        """The global/forced default (per-org value is via effective_rpm)."""
        return self._rpm

    def effective_rpm(self, org_id: str) -> int:
        """The org's RPM: a forced value, else its org_quotas override, else the
        global default. Cached with a short TTL; fail-open on any DB error."""
        if self._forced_rpm is not None:
            return self._forced_rpm
        hit = _QUOTA_CACHE.get(org_id)
        if hit is not None and hit[1] > time.monotonic():
            override = hit[0]
        else:
            override = _resolve_org_rpm(org_id)
            _QUOTA_CACHE[org_id] = (override, time.monotonic() + _QUOTA_TTL_S)
        return override if override is not None else self._rpm

    def _r(self):
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(
                settings.redis_url, socket_timeout=0.25, socket_connect_timeout=0.25,
                decode_responses=True,
            )
        return self._client

    def acquire(self, org_id: str, provider: str, tier: str) -> bool:
        """True if the call may proceed. One INCR per attempt; fail-open."""
        try:
            rpm = self.effective_rpm(org_id)
            minute = int(time.time() // 60)
            key = f"llm:{org_id}:{provider}:{tier}:rpm:{minute}"
            r = self._r()
            n = r.incr(key)
            if n == 1:
                r.expire(key, 60)
            return n <= rpm
        except Exception:
            return True


def _resolve_org_rpm(org_id: str) -> int | None:
    """org_quotas.rpm_limit for an org (or None). DB-gated + fail-soft."""
    import uuid

    try:
        uuid.UUID(str(org_id))
    except (ValueError, TypeError):
        return None
    if getattr(settings, "task_store", "memory") != "postgres":
        return None
    try:
        from sqlalchemy import text

        from ..db.rls import set_org_context
        from ..db.session import get_sync_engine

        with get_sync_engine(settings).begin() as conn:
            set_org_context(conn, org_id)
            return conn.execute(
                text("select rpm_limit from org_quotas where org_id = :o"),
                {"o": org_id},
            ).scalar()
    except Exception:
        return None


_rate_limit: RateLimit | None = None


def get_rate_limit() -> RateLimit:
    global _rate_limit
    if _rate_limit is None:
        _rate_limit = RateLimit()
    return _rate_limit


def set_rate_limit(rl: RateLimit | None) -> None:
    """Tests inject a limiter over a fake client; None restores the default."""
    global _rate_limit
    _rate_limit = rl
