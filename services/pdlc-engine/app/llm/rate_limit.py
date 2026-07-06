"""Per-tenant fixed-window RPM limiter (Redis).

Key: `llm:{org_id}:{provider}:{tier}:rpm:{epoch_minute}` — INCR + EXPIRE 60,
compared against the org's RPM. Fixed-window (not sliding) is deliberate: one
round-trip on the hot path, and burst-at-the-boundary error is acceptable for
a quota knob. Acquire happens once per ATTEMPT (each failover attempt is a
real upstream call, so it must count against the quota).

Disabled unless PDLC_RATE_LIMIT_ENABLED; per-org RPM overrides arrive with the
Nexus "Quotas" page (Phase H) — until then `PDLC_LLM_RPM_DEFAULT` applies to
every org. FAIL-OPEN on Redis errors (a broken limiter must not become the
outage).
"""

from __future__ import annotations

import logging
import time

from ..config import settings

log = logging.getLogger("pdlc.llm.ratelimit")


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
        self._rpm = rpm if rpm is not None else getattr(settings, "llm_rpm_default", 60)

    @property
    def rpm(self) -> int:
        return self._rpm

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
            minute = int(time.time() // 60)
            key = f"llm:{org_id}:{provider}:{tier}:rpm:{minute}"
            r = self._r()
            n = r.incr(key)
            if n == 1:
                r.expire(key, 60)
            return n <= self._rpm
        except Exception:
            return True


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
