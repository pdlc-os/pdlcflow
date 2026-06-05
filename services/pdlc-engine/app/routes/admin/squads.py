"""Per-squad scoreboard with period-over-period deltas."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...analytics import get_analytics_store

router = APIRouter(prefix="/squads", tags=["admin", "squads"])


@router.get("/scoreboard")
def scoreboard(
    org_id: str = Query(...),
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> dict:
    rows = get_analytics_store().rollup(
        org_id=org_id, dimension="squad", frm=frm, to=to
    )
    return {"rows": rows}
