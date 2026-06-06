"""Time-travel view of one feature — every event in chronological order, replayable."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...analytics import get_analytics_store
from ._guard import admin_org

router = APIRouter(prefix="/features", tags=["admin", "features"])


@router.get("/{roadmap_id}/timeline")
def timeline(roadmap_id: str, org_id: str = Depends(admin_org("/admin/features/timeline"))) -> dict:
    events = get_analytics_store().feature_timeline(
        org_id=org_id, roadmap_id=roadmap_id
    )
    return {"roadmap_id": roadmap_id, "events": events}
