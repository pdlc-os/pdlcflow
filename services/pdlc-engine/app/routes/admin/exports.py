"""CSV / ClickHouse query / DDL export for BI integration."""

from fastapi import APIRouter

router = APIRouter(prefix="/exports", tags=["admin", "exports"])


@router.get("/csv")
def export_csv(view: str) -> dict:
    return {"view": view, "ready": False, "phase": "A stub"}
