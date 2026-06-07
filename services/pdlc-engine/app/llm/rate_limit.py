"""Per-tenant token bucket rate limiter.

Key: `llm:{org_id}:{provider}:{tier}:rpm`. Each LLM call increments and
checks against the configured RPM. Buckets are set at tenant onboarding; the
Nexus Console "Quotas" page exposes the knobs (Phase H).
"""

from __future__ import annotations


class RateLimit:
    def __init__(self, redis_client, rpm: int = 60):
        self._redis = redis_client
        self._rpm = rpm

    async def acquire(self, org_id: str, provider: str, tier: str) -> bool:
        # Phase A stub: always allow. Real impl INCRs the per-minute slot key
        # `llm:{org_id}:{provider}:{tier}:rpm:{epoch_minute}` in Redis with
        # EXPIRE 60 and compares the count against `self._rpm`.
        return True
