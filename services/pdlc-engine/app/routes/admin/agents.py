"""Per-persona heatmap — usage, token spend, approval rate, P0 finding rate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...analytics import get_analytics_store
from ...auth.local import Identity, get_principal

router = APIRouter(prefix="/agents", tags=["admin", "agents"])

PERSONAS = [
    "atlas", "bolt", "echo", "friday", "jarvis",
    "muse", "neo", "phantom", "pulse", "sentinel",
]


@router.get("/heatmap")
def heatmap(
    org_id: str | None = Query(None),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    # The persona list is org-independent (it names the 10 fixed agents), so the
    # route renders without an org_id. Cells require an org — without one we keep
    # the cross-org ban and return an empty cell set rather than scanning.
    if principal is not None:  # auth on: scope cells strictly to the caller's org
        org_id = principal.org_id
    cells = (
        get_analytics_store().rollup(org_id=org_id, dimension="agent")
        if org_id
        else []
    )
    return {"personas": PERSONAS, "cells": cells}
