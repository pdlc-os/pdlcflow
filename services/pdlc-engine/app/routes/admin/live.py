"""Live mode — sampled real-time event feed across all squads in the org."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...analytics import get_analytics_store
from ._guard import require_org

router = APIRouter(prefix="/live", tags=["admin", "live"])


@router.get("")
def live(org_id: str | None = Query(None), limit: int = Query(50)) -> dict:
    org_id = require_org(org_id, "/admin/live")
    events = get_analytics_store().live(org_id=org_id, limit=limit)
    return {"events": events}
