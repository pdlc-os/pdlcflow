"""Context-window usage — how close agent prompts came to the active model's
limit (per org, optionally scoped to a project). Powers the Studio context meter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...analytics import get_analytics_store
from ._guard import admin_org

router = APIRouter(prefix="/context", tags=["admin", "context"])


@router.get("")
def context_usage(
    org_id: str = Depends(admin_org("/admin/context")),
    project_id: str | None = Query(None),
) -> dict:
    return get_analytics_store().context_usage(org_id=org_id, project_id=project_id)
