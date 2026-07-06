"""Nexus Console — pricing overrides + org budgets (PRD-07).

Estimates are for dashboards only — NEVER used for billing decisions (the
long-standing pricing.py disclaimer; it also renders in the console). The
effective price sheet is catalog + preset hints + org overrides, provenance-
tagged so admins can see where each number comes from.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from ...auth.local import Identity, get_principal
from ...db.rls import set_org_context
from ...llm.factory import invalidate_pricing_cache
from ...llm.presets import load_catalog
from ...llm.pricing import catalog_prices, catalog_version
from ._guard import admin_org
from .models import _audit, _engine, record_version

router = APIRouter(prefix="/pricing", tags=["admin", "pricing"])
budget_router = APIRouter(prefix="/budget", tags=["admin", "budget"])


def validate_overrides(overrides: dict) -> None:
    """Shape check, DB-free: {"provider/model": {"in": >=0, "out": >=0}}."""
    for key, price in overrides.items():
        if "/" not in key:
            raise HTTPException(status_code=422,
                                detail=f"override key {key!r} must be provider/model_id")
        if (not isinstance(price, dict) or set(price) != {"in", "out"}
                or any(not isinstance(price[k], int | float) or price[k] < 0
                       for k in ("in", "out"))):
            raise HTTPException(
                status_code=422,
                detail=f"override {key!r} must be {{'in': $/1M >= 0, 'out': $/1M >= 0}}")


def effective_sheet(overrides: dict | None) -> dict[str, dict]:
    """Catalog + preset hints + org overrides, each entry provenance-tagged."""
    sheet: dict[str, dict] = {}
    for key, p in catalog_prices().items():
        sheet[key] = {"in": p["in"], "out": p["out"], "source": "catalog"}
    for preset in load_catalog().presets:
        for model_id, hint in preset.pricing_hints.items():
            key = f"{preset.provider}/{model_id}"
            sheet.setdefault(key, {"in": hint["in"], "out": hint["out"],
                                   "source": "preset"})
    for key, p in (overrides or {}).items():
        sheet[key] = {"in": p["in"], "out": p["out"], "source": "override"}
    return sheet


@router.get("")
def get_pricing(org_id: str = Depends(admin_org("/admin/pricing"))) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        overrides = conn.execute(
            text("select pricing_override from org_llm_config where org_id = :o"),
            {"o": org_id},
        ).scalar()
    return {
        "catalog_version": catalog_version(),
        "disclaimer": "Estimates for dashboards only — never used for billing.",
        "effective": effective_sheet(overrides),
    }


@router.put("/overrides")
def put_overrides(
    overrides: dict[str, dict],
    org_id: str = Depends(admin_org("/admin/pricing")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    """Full-replace of the org's override sheet (delete a key by omitting it)."""
    validate_overrides(overrides)
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        exists = conn.execute(
            text("select 1 from org_llm_config where org_id = :o"), {"o": org_id}
        ).scalar()
        if not exists:
            raise HTTPException(
                status_code=409,
                detail="configure the org's provider first (Settings → Models) — "
                       "pricing overrides attach to the org model config")
        record_version(conn, org_id, "org", "update", principal)
        conn.execute(
            text("update org_llm_config set pricing_override = cast(:po as jsonb) "
                 "where org_id = :o"),
            {"o": org_id, "po": json.dumps(overrides) if overrides else None},
        )
    invalidate_pricing_cache(org_id)
    _audit("llm_config.changed", org_id,
           {"scope": "org", "change_kind": "update", "what": "pricing_override",
            "keys": len(overrides)})
    return {"ok": True, "keys": len(overrides)}


class Budget(BaseModel):
    monthly_limit_usd: float = Field(gt=0)
    alert_pcts: list[int] = Field(default=[50, 80, 100], max_length=10)


@budget_router.get("")
def get_budget(org_id: str = Depends(admin_org("/admin/budget"))) -> dict | None:
    month_start = datetime.now(UTC).date().replace(day=1)
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        row = conn.execute(
            text("select monthly_limit_usd, alert_pcts from org_budgets "
                 "where org_id = :o"),
            {"o": org_id},
        ).mappings().first()
        if not row:
            return None
        spent = conn.execute(
            text("select coalesce(sum((payload->>'usd_estimate')::float), 0) "
                 "from events where org_id = :o and event_type = 'llm.tokens_spent' "
                 "and ts >= :m"),
            {"o": org_id, "m": month_start},
        ).scalar() or 0.0
        fired = conn.execute(
            text("select pct from org_budget_alerts "
                 "where org_id = :o and month = :m order by pct"),
            {"o": org_id, "m": month_start},
        ).scalars().all()
    return {
        "monthly_limit_usd": float(row["monthly_limit_usd"]),
        "alert_pcts": row["alert_pcts"],
        "month_to_date_usd": round(float(spent), 4),
        "fired": list(fired),
    }


@budget_router.put("")
def put_budget(
    budget: Budget,
    org_id: str = Depends(admin_org("/admin/budget")),
) -> dict:
    if any(p <= 0 or p > 1000 for p in budget.alert_pcts):
        raise HTTPException(status_code=422, detail="alert_pcts must be in (0, 1000]")
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        conn.execute(
            text("insert into org_budgets (org_id, monthly_limit_usd, alert_pcts, updated_at) "
                 "values (:o, :l, cast(:p as jsonb), now()) "
                 "on conflict (org_id) do update set "
                 "monthly_limit_usd = excluded.monthly_limit_usd, "
                 "alert_pcts = excluded.alert_pcts, updated_at = now()"),
            {"o": org_id, "l": budget.monthly_limit_usd,
             "p": json.dumps(sorted(set(budget.alert_pcts)))},
        )
    _audit("budget.configured", org_id,
           {"monthly_limit_usd": budget.monthly_limit_usd,
            "alert_pcts": sorted(set(budget.alert_pcts))})
    return {"ok": True}
