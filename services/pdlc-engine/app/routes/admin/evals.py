"""Eval scores — average score + pass rate per eval and per agent (Phase J)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...analytics import get_analytics_store
from ._guard import require_org

router = APIRouter(prefix="/evals", tags=["admin", "evals"])


@router.get("/summary")
def summary(org_id: str | None = Query(None)) -> dict:
    org_id = require_org(org_id, "/admin/evals/summary")
    return get_analytics_store().eval_summary(org_id=org_id)
