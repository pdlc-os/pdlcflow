"""Nexus Console — work narrative.

Given a date window (and optional project), returns clickstream **stats** split
by human / agent / system plus an LLM-generated **narrative** of the work done.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pdlc_graph.ports import reset_current_org, set_current_org

from ...analytics import get_analytics_store
from ...narrative import build_narrative
from ._guard import admin_org

router = APIRouter(prefix="/narrative", tags=["admin", "narrative"])


@router.get("")
def narrative(
    org_id: str = Depends(admin_org("/admin/narrative")),
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    project_id: str | None = Query(None),
) -> dict:
    summary = get_analytics_store().work_summary(
        org_id=org_id, frm=frm, to=to, project_id=project_id
    )
    tok = set_current_org(org_id)  # bind tenant so the org's LLM provider/tier apply
    try:
        text = build_narrative(summary)
    finally:
        reset_current_org(tok)
    return {"summary": summary, "narrative": text}
