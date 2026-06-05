"""Backfill historical events from episodes + decisions + phase history.

Each synthetic event carries `payload.synthetic = true` so admin dashboards
can distinguish live vs reconstructed activity. Re-running is idempotent —
the engine dedups on (org_id, event_id) and the IDs are derived from
content hashes, so the second pass writes nothing new.
"""

from __future__ import annotations

from pathlib import Path


def backfill_events(_project_root: Path, _engine_url: str) -> int:
    """Phase A stub. Real impl: read each episode markdown, parse the metrics
    table, emit phase.entered / phase.exited / deploy.succeeded / strike.recorded
    events with timestamps drawn from the episode."""
    return 0
