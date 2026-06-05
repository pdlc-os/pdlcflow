"""Domain rollups — same metrics as initiatives, sliced by cross-cutting tag."""

from fastapi import APIRouter

router = APIRouter(prefix="/domains", tags=["admin", "domains"])


@router.get("/rollup")
def rollup() -> dict:
    return {"rows": [], "phase": "A stub"}
