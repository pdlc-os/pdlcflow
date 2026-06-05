"""Live mode — sampled real-time event feed across all squads in the org."""

from fastapi import APIRouter

router = APIRouter(prefix="/live", tags=["admin", "live"])


@router.get("/recent")
def recent() -> dict:
    return {"events": [], "phase": "A stub"}
