"""Budget threshold alerts (PRD-07) — soft, estimate-based, best-effort.

Evaluated on the clickstream drain path after a batch lands: for each org with
`llm.tokens_spent` events in the batch (memoized — at most one evaluation per
org per 5 minutes), month-to-date estimated spend is compared to the org's
budget. Crossing a threshold inserts into the `org_budget_alerts` ledger — its
primary key is the dedupe, so concurrent workers fire each (org, month, pct)
exactly once — and emits a `budget.threshold` event.

Everything here is fail-silent: alerting must never slow or break ingestion.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

log = logging.getLogger("pdlc.clickstream.budget")

_CHECK_INTERVAL_S = 300.0
_last_check: dict[str, float] = {}


def thresholds_crossed(spent: float, limit: float, alert_pcts: list[int],
                       already_fired: list[int]) -> list[int]:
    """Pure decision: which configured thresholds has spend crossed that have
    not fired yet this month."""
    if limit <= 0:
        return []
    return sorted(
        pct for pct in set(alert_pcts)
        if pct not in set(already_fired) and spent >= limit * pct / 100.0
    )


def reset_budget_memo() -> None:
    _last_check.clear()


def check_budgets(batch: list) -> None:
    """Called by the emitter drain after a batch is written."""
    try:
        orgs = {str(e.org_id) for e in batch if e.event_type == "llm.tokens_spent"}
    except Exception:
        return
    now = time.monotonic()
    for org in orgs:
        if now - _last_check.get(org, -_CHECK_INTERVAL_S) < _CHECK_INTERVAL_S:
            continue
        _last_check[org] = now
        try:
            _evaluate(org)
        except Exception as exc:  # alerts are best-effort, ingestion is sacred
            log.debug("budget check skipped for org: %s", type(exc).__name__)


def _evaluate(org: str) -> None:
    from ..config import settings
    from ..db.rls import set_org_context
    from ..db.session import get_sync_engine

    month_start = datetime.now(UTC).date().replace(day=1)
    fired_now: list[tuple[int, float, float]] = []
    with get_sync_engine(settings).begin() as conn:
        set_org_context(conn, org)
        b = conn.execute(
            text("select monthly_limit_usd, alert_pcts from org_budgets "
                 "where org_id = :o"),
            {"o": org},
        ).mappings().first()
        if not b:
            return
        limit = float(b["monthly_limit_usd"])
        spent = float(conn.execute(
            text("select coalesce(sum((payload->>'usd_estimate')::float), 0) "
                 "from events where org_id = :o and event_type = 'llm.tokens_spent' "
                 "and ts >= :m"),
            {"o": org, "m": month_start},
        ).scalar() or 0.0)
        already = conn.execute(
            text("select pct from org_budget_alerts where org_id = :o and month = :m"),
            {"o": org, "m": month_start},
        ).scalars().all()
        for pct in thresholds_crossed(spent, limit, list(b["alert_pcts"]), list(already)):
            inserted = conn.execute(
                text("insert into org_budget_alerts (org_id, month, pct) "
                     "values (:o, :m, :p) on conflict do nothing returning pct"),
                {"o": org, "m": month_start, "p": pct},
            ).scalar()
            if inserted is not None:  # we won the race — we emit the event
                fired_now.append((pct, spent, limit))

    if fired_now:
        from .emitter import get_emitter

        for pct, spent, limit in fired_now:
            try:
                get_emitter().emit(
                    "budget.threshold",
                    {"org_id": uuid.UUID(org), "project_id": uuid.UUID(int=0),
                     "actor": "system"},
                    {"pct": pct, "month": month_start.strftime("%Y-%m"),
                     "spent_usd": round(spent, 2), "limit_usd": limit},
                    str(uuid.uuid4()),
                )
            except Exception:
                pass
        log.info("budget thresholds fired for org: %s",
                 [pct for pct, _, _ in fired_now])
