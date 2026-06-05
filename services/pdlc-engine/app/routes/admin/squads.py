"""Per-squad scoreboard with period-over-period deltas."""

from fastapi import APIRouter

router = APIRouter(prefix="/squads", tags=["admin", "squads"])


@router.get("/scoreboard")
def scoreboard() -> dict:
    return {"rows": [], "phase": "A stub"}
