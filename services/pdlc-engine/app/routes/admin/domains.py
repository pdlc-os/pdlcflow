"""Domain rollups — same metrics as initiatives, sliced by cross-cutting tag."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...analytics import get_analytics_store
from ._guard import admin_org

router = APIRouter(prefix="/domains", tags=["admin", "domains"])


@router.get("/rollup")
def rollup(
    org_id: str = Depends(admin_org("/admin/domains/rollup")),
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> dict:
    rows = get_analytics_store().rollup(
        org_id=org_id, dimension="domain", frm=frm, to=to
    )
    return {"rows": rows}
