"""Initiative rollups — spend, cycle time, features delivered, agent usage."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...analytics import get_analytics_store
from ._guard import require_org

router = APIRouter(prefix="/initiatives", tags=["admin", "initiatives"])


@router.get("/rollup")
def rollup(
    org_id: str | None = Query(None),
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> dict:
    org_id = require_org(org_id, "/admin/initiatives/rollup")
    rows = get_analytics_store().rollup(
        org_id=org_id, dimension="initiative", frm=frm, to=to
    )
    return {"rows": rows}
