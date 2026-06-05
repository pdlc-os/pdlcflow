"""Per-tenant token bucket rate limiter.

Key: `llm:{org_id}:{provider}:{tier}:rpm`. Each LLM call increments and
checks against the configured RPM. Buckets are set at tenant onboarding; the
Atlas Console "Quotas" page exposes the knobs (Phase H).
"""

from __future__ import annotations

import time


class RateLimit:
    def __init__(self, redis_client, rpm: int = 60):
        self._redis = redis_client
        self._rpm = rpm

    async def acquire(self, org_id: str, provider: str, tier: str) -> bool:
        key = f"llm:{org_id}:{provider}:{tier}:rpm"
        window = int(time.time() // 60)
        slot = f"{key}:{window}"
        # Phase A stub: always allow. Real impl uses Redis INCR + EXPIRE 60.
        return True
