"""Per-squad scoreboard with period-over-period deltas."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...analytics import get_analytics_store
from ._guard import require_org

router = APIRouter(prefix="/squads", tags=["admin", "squads"])


@router.get("/scoreboard")
def scoreboard(
    org_id: str | None = Query(None),
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> dict:
    org_id = require_org(org_id, "/admin/squads/scoreboard")
    rows = get_analytics_store().rollup(
        org_id=org_id, dimension="squad", frm=frm, to=to
    )
    return {"rows": rows}
