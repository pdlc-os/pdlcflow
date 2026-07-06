"""Circuit breaker per (org, provider[:endpoint-host]) — Redis-backed, TTL'd.

After `threshold` failures inside `window_s`, the breaker OPENS for
`cooldown_s` (candidates are skipped, so a dead provider costs one timeout per
cooldown, not one per call). When the open TTL lapses the breaker is HALF-OPEN:
exactly one probe call is admitted (SET NX token); success closes it, failure
re-opens. All state lives in TTL'd Redis keys, so it self-heals and needs no
janitor.

Keyed per-org so one org's bad `openai_compatible` gateway never trips another
org's view of the same provider name (gateway keys also carry the endpoint
host — see `breaker_key`).

FAIL-OPEN by design: if Redis is down or slow, `allow()` returns True and the
recorders no-op — the resilience machinery must never be the outage. The unit
tier runs Redis-free through the injectable client.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from ..config import settings

log = logging.getLogger("pdlc.llm.breaker")


def breaker_key(provider: str, endpoint: str | None) -> str:
    """Gateways (openai_compatible) are distinguished by endpoint host — two
    different gateways must not share a breaker just because the provider
    *name* matches."""
    if provider == "openai_compatible" and endpoint:
        host = urlparse(endpoint).hostname or "unknown"
        return f"{provider}:{host}"
    return provider


class CircuitBreaker:
    def __init__(self, redis_client=None, *, threshold: int | None = None,
                 window_s: int | None = None, cooldown_s: int | None = None,
                 on_transition=None) -> None:
        self._client = redis_client
        self._threshold = threshold or getattr(settings, "llm_breaker_threshold", 5)
        self._window = window_s or getattr(settings, "llm_breaker_window_s", 60)
        self._cooldown = cooldown_s or getattr(settings, "llm_breaker_cooldown_s", 30)
        self._on_transition = on_transition  # fn(key, transition) for telemetry

    def _r(self):
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(
                settings.redis_url, socket_timeout=0.25, socket_connect_timeout=0.25,
                decode_responses=True,
            )
        return self._client

    @staticmethod
    def _k(org: str, key: str, leaf: str) -> str:
        return f"llm:cb:{org}:{key}:{leaf}"

    def allow(self, org: str, key: str) -> bool:
        try:
            r = self._r()
            if r.get(self._k(org, key, "state")) == "open":
                return False
            if r.get(self._k(org, key, "half")):
                # Half-open window: admit exactly one probe.
                return bool(r.set(self._k(org, key, "probe"), "1", nx=True, ex=10))
            return True
        except Exception:  # Redis down/slow → fail open
            return True

    def record_failure(self, org: str, key: str) -> None:
        try:
            r = self._r()
            if r.get(self._k(org, key, "half")) and not r.get(self._k(org, key, "state")):
                # The half-open probe failed → re-open.
                r.set(self._k(org, key, "state"), "open", ex=self._cooldown)
                r.set(self._k(org, key, "half"), "1", ex=self._cooldown * 2)
                r.delete(self._k(org, key, "probe"))
                self._transition(key, "reopen")
                return
            fails = self._k(org, key, "fails")
            n = r.incr(fails)
            if n == 1:
                r.expire(fails, self._window)
            if n >= self._threshold and not r.get(self._k(org, key, "state")):
                r.set(self._k(org, key, "state"), "open", ex=self._cooldown)
                r.set(self._k(org, key, "half"), "1", ex=self._cooldown * 2)
                r.delete(fails)
                self._transition(key, "open")
        except Exception:
            pass

    def record_success(self, org: str, key: str) -> None:
        try:
            r = self._r()
            was_half = bool(r.get(self._k(org, key, "half")))
            r.delete(self._k(org, key, "fails"), self._k(org, key, "state"),
                     self._k(org, key, "half"), self._k(org, key, "probe"))
            if was_half:
                self._transition(key, "close")
        except Exception:
            pass

    def _transition(self, key: str, transition: str) -> None:
        log.info("breaker %s → %s", key, transition)
        if self._on_transition is not None:
            try:
                self._on_transition(key, transition)
            except Exception:
                pass


_breaker: CircuitBreaker | None = None


def get_breaker() -> CircuitBreaker:
    global _breaker
    if _breaker is None:
        from .. import observability

        _breaker = CircuitBreaker(on_transition=observability.record_breaker)
    return _breaker


def set_breaker(breaker: CircuitBreaker | None) -> None:
    """Tests inject a breaker over a fake client; None restores the default."""
    global _breaker
    _breaker = breaker
