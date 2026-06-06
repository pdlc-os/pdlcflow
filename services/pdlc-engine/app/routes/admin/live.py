"""Live mode — sampled real-time event feed across all squads in the org."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...analytics import get_analytics_store
from ._guard import admin_org

router = APIRouter(prefix="/live", tags=["admin", "live"])


@router.get("")
def live(org_id: str = Depends(admin_org("/admin/live")), limit: int = Query(50)) -> dict:
    events = get_analytics_store().live(org_id=org_id, limit=limit)
    return {"events": events}
