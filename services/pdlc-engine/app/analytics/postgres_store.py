"""Postgres analytics read store — rollups over the `events` table.

Implements the same interface as the in-memory `AnalyticsStore` but answers
from SQL, so admin rollups survive restarts and span every process that wrote
events (via the PostgresSink). Token/USD metrics are extracted from the event
payload jsonb. Every query is org-scoped (cross-org analytics banned, §5.3).

Verified via docker-compose (no Postgres in CI).
"""

from __future__ import annotations

import logging

from event_schema import actor_type_for
from sqlalchemy import text

from ..db.rls import set_org_context
from ..db.session import get_sync_engine
from .store import _require_org, context_usage_from, summarize_work  # cross-org guard + helpers

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
            set_org_context(conn, org_id)
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
            set_org_context(conn, org_id)
            rows = conn.execute(sql, {"org": org_id, "rid": roadmap_id}).mappings().all()
        return [dict(r) for r in rows]

    def live(self, *, org_id, limit=50) -> list[dict]:
        org_id = _require_org(org_id)
        sql = text(
            "select event_type, ts, roadmap_id, actor, payload from events "
            "where org_id = :org order by ts desc limit :lim"
        )
        with self._engine.begin() as conn:
            set_org_context(conn, org_id)
            rows = conn.execute(sql, {"org": org_id, "lim": limit}).mappings().all()
        return [dict(r) for r in rows]

    def eval_summary(self, *, org_id) -> dict:
        org_id = _require_org(org_id)

        def _agg(group_expr: str) -> dict:
            sql = text(
                f"select {group_expr} as k, count(*) as n, "
                f"avg((payload->>'score')::float) as avg_score, "
                f"avg(case when (payload->>'passed')::boolean then 1.0 else 0.0 end) as pass_rate "
                f"from events where org_id = :org and event_type = 'eval.scored' "
                f"and {group_expr} is not null group by 1"
            )
            with self._engine.begin() as conn:
                set_org_context(conn, org_id)
                rows = conn.execute(sql, {"org": org_id}).mappings().all()
            return {
                r["k"]: {"n": int(r["n"]), "avg_score": round(float(r["avg_score"] or 0), 4),
                         "pass_rate": round(float(r["pass_rate"] or 0), 4)}
                for r in rows
            }

        return {"by_eval": _agg("payload->>'eval_id'"), "by_agent": _agg("payload->>'target'")}

    def totals(self, *, org_id) -> dict:
        org_id = _require_org(org_id)
        sql = text(
            f"select count(*) as events, sum({_TOKENS}) as tokens, sum({_USD}) as usd "
            f"from events where org_id = :org"
        )
        with self._engine.begin() as conn:
            set_org_context(conn, org_id)
            r = conn.execute(sql, {"org": org_id}).mappings().one()
        return {"events": int(r["events"] or 0), "tokens": int(r["tokens"] or 0),
                "usd": round(float(r["usd"] or 0), 6)}

    def work_summary(self, *, org_id, frm=None, to=None, project_id=None) -> dict:
        org_id = _require_org(org_id)
        clauses = ["org_id = :org"]
        params: dict = {"org": org_id}
        if frm:
            clauses.append("ts >= :frm")
            params["frm"] = frm
        if to:
            clauses.append("ts <= :to")
            params["to"] = to
        if project_id:
            clauses.append("project_id = :pid")
            params["pid"] = str(project_id)
        sql = text(
            f"select event_type, ts, actor, roadmap_id, "
            f"payload->>'agent_persona' as agent_persona, "
            f"{_TOKENS} as tokens, {_USD} as usd "
            f"from events where {' and '.join(clauses)} order by ts asc limit 20000"
        )
        with self._engine.begin() as conn:
            set_org_context(conn, org_id)
            raw = conn.execute(sql, params).mappings().all()
        rows = [
            {
                "event_type": r["event_type"],
                "ts": r["ts"].isoformat() if hasattr(r["ts"], "isoformat") else str(r["ts"]),
                "actor": r["actor"],
                "actor_type": actor_type_for(r["event_type"]),
                "roadmap_id": r["roadmap_id"],
                "agent_persona": r["agent_persona"],
                "tokens": int(r["tokens"] or 0),
                "usd": float(r["usd"] or 0),
            }
            for r in raw
        ]
        return {
            "window": {"from": frm, "to": to},
            "project_id": str(project_id) if project_id else None,
            **summarize_work(rows),
        }

    def context_usage(self, *, org_id, project_id=None) -> dict:
        org_id = _require_org(org_id)
        clauses = ["org_id = :org", "event_type = 'llm.tokens_spent'"]
        params: dict = {"org": org_id}
        if project_id:
            clauses.append("project_id = :pid")
            params["pid"] = str(project_id)
        sql = text(
            f"select ts, payload->>'model_id' as model_id, "
            f"coalesce((payload->>'tokens_in')::int,0) as tokens_in, {_TOKENS} as tokens "
            f"from events where {' and '.join(clauses)} order by ts asc"
        )
        with self._engine.begin() as conn:
            set_org_context(conn, org_id)
            raw = conn.execute(sql, params).mappings().all()
        rows = [
            {"event_type": "llm.tokens_spent",
             "ts": r["ts"].isoformat() if hasattr(r["ts"], "isoformat") else str(r["ts"]),
             "model_id": r["model_id"], "tokens_in": int(r["tokens_in"] or 0),
             "tokens": int(r["tokens"] or 0)}
            for r in raw
        ]
        return context_usage_from(rows)
