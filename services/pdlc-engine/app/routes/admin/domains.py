"""Domain rollups — same metrics as initiatives, sliced by cross-cutting tag."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...analytics import get_analytics_store

router = APIRouter(prefix="/domains", tags=["admin", "domains"])


@router.get("/rollup")
def rollup(
    org_id: str = Query(...),
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> dict:
    rows = get_analytics_store().rollup(
        org_id=org_id, dimension="domain", frm=frm, to=to
    )
    return {"rows": rows}
