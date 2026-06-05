"""Initiative rollups — spend, cycle time, features delivered, agent usage."""

from fastapi import APIRouter

router = APIRouter(prefix="/initiatives", tags=["admin", "initiatives"])


@router.get("/rollup")
def rollup(from_: str | None = None, to: str | None = None) -> dict:
    return {"rows": [], "phase": "A stub", "range": [from_, to]}
