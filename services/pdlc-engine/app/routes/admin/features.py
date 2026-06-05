"""Time-travel view of one feature — every event in chronological order, replayable."""

from fastapi import APIRouter

router = APIRouter(prefix="/features", tags=["admin", "features"])


@router.get("/{feature_id}/timeline")
def timeline(feature_id: str) -> dict:
    return {"feature_id": feature_id, "events": [], "phase": "A stub"}
