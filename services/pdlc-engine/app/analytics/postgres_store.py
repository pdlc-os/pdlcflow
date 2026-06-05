"""Postgres analytics read store — rollups over the `events` table.

Implements the same interface as the in-memory `AnalyticsStore` but answers
from SQL, so admin rollups survive restarts and span every process that wrote
events (via the PostgresSink). Token/USD metrics are extracted from the event
payload jsonb. Every query is org-scoped (cross-org analytics banned, §5.3).

Verified via docker-compose (no Postgres in CI).
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from ..db.session import get_sync_engine
from .store import _require_org  # reuse the cross-org guard

log = logging.getLogger("pdlc.analytics.postgres")

# dimension -> the SQL grouping expression over the events table.
_DIM_SQL = {
    "initiative": "initiative_id::text",
    "application": "application_id::text",
    "squad": "squad_id::text",
    "roadmap": "roadmap_id",
    "user_story": "user_story_id",
    "agent": "payload->>'agent_persona'",
}
_TOKENS = "coalesce((payload->>'tokens_in')::int,0)+coalesce((payload->>'tokens_out')::int,0)"
_USD = "coalesce((payload->>'usd_estimate')::float,0)"


class PostgresAnalyticsStore:
    def __init__(self, settings) -> None:
        self._engine = get_sync_engine(settings)

    # write(batch) so the store can double as a clickstream sink if desired.
    def write(self, batch) -> None:  # pragma: no cover - PostgresSink owns writes
        return None

    def ingest(self, batch) -> None:  # pragma: no cover - PostgresSink owns writes
        return None

    def rollup(self, *, org_id, dimension, frm=None, to=None) -> list[dict]:
        org_id = _require_org(org_id)
        if dimension == "domain":
            select_key = "unnest(domains)"
            group = "1"
        elif dimension in _DIM_SQL:
            select_key = _DIM_SQL[dimension]
            group = "1"
        else:
            raise ValueError(f"unknown dimension {dimension!r}")
        clauses = ["org_id = :org", f"{select_key} is not null"]
        params: dict = {"org": org_id}
        if frm:
            clauses.append("ts >= :frm")
            params["frm"] = frm
        if to:
            clauses.append("ts <= :to")
            params["to"] = to
        sql = text(
            f"select {select_key} as key, count(*) as events, "
            f"sum({_TOKENS}) as tokens, sum({_USD}) as usd "
            f"from events where {' and '.join(clauses)} group by {group} "
            f"order by events desc"
        )
        with self._engine.begin() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [
            {"key": r["key"], "events": int(r["events"]),
             "tokens": int(r["tokens"] or 0), "usd": round(float(r["usd"] or 0), 6)}
            for r in rows
        ]

    def feature_timeline(self, *, org_id, roadmap_id) -> list[dict]:
        org_id = _require_org(org_id)
        sql = text(
            "select event_type, ts, roadmap_id, actor, payload from events "
            "where org_id = :org and roadmap_id = :rid order by ts asc"
        )
        with self._engine.begin() as conn:
            rows = conn.execute(sql, {"org": org_id, "rid": roadmap_id}).mappings().all()
        return [dict(r) for r in rows]

    def live(self, *, org_id, limit=50) -> list[dict]:
        org_id = _require_org(org_id)
        sql = text(
            "select event_type, ts, roadmap_id, actor, payload from events "
            "where org_id = :org order by ts desc limit :lim"
        )
        with self._engine.begin() as conn:
            rows = conn.execute(sql, {"org": org_id, "lim": limit}).mappings().all()
        return [dict(r) for r in rows]

    def totals(self, *, org_id) -> dict:
        org_id = _require_org(org_id)
        sql = text(
            f"select count(*) as events, sum({_TOKENS}) as tokens, sum({_USD}) as usd "
            f"from events where org_id = :org"
        )
        with self._engine.begin() as conn:
            r = conn.execute(sql, {"org": org_id}).mappings().one()
        return {"events": int(r["events"] or 0), "tokens": int(r["tokens"] or 0),
                "usd": round(float(r["usd"] or 0), 6)}
