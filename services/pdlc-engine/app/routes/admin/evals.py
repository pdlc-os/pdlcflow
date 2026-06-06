"""Eval scores — average score + pass rate per eval and per agent (Phase J)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...analytics import get_analytics_store
from ._guard import admin_org

router = APIRouter(prefix="/evals", tags=["admin", "evals"])


@router.get("/summary")
def summary(org_id: str = Depends(admin_org("/admin/evals/summary"))) -> dict:
    return get_analytics_store().eval_summary(org_id=org_id)
