"""Analytics read store — the query side of the clickstream.

The emitter feeds every event here (in addition to the durable sink); the Atlas
Console admin routes query it for rollups. In-memory by default so the whole
dashboard works hermetically in tests and single-process dev; the engine
injects the Postgres-backed store at boot for SaaS/self-host (a
ClickHouse store is a possible future scale-up; none exists today).

Cross-org analytics are banned by design (plan §5.3): every query REQUIRES an
`org_id` and only ever scans that org's events.
"""

from __future__ import annotations

from typing import Protocol

from event_schema import EventEnvelope, actor_type_for

# Dimension name → the flattened event field it groups by. "domain" explodes the
# domains list; "agent" reads payload.agent_persona.
_DIMENSIONS = {
    "initiative": "initiative_id",
    "application": "application_id",
    "squad": "squad_id",
    "domain": "domains",
    "roadmap": "roadmap_id",
    "user_story": "user_story_id",
    "agent": "agent_persona",
}

METRICS = ("events", "tokens", "usd")


def _flatten(e: EventEnvelope) -> dict:
    p = e.payload or {}
    return {
        "event_id": str(e.event_id),
        "event_type": e.event_type,
        "ts": e.ts.isoformat(),
        "org_id": str(e.org_id),
        "squad_id": str(e.squad_id) if e.squad_id else None,
        "initiative_id": str(e.initiative_id) if e.initiative_id else None,
        "application_id": str(e.application_id) if e.application_id else None,
        "project_id": str(e.project_id) if e.project_id else None,
        "domains": list(e.domains or []),
        "roadmap_id": e.roadmap_id,
        "prd_id": e.prd_id,
        "user_story_id": e.user_story_id,
        "plan_step": e.plan_step,
        "actor": e.actor,
        "actor_type": e.actor_type or actor_type_for(e.event_type),
        "agent_persona": p.get("agent_persona"),
        "model_id": p.get("model_id"),
        "tokens_in": int(p.get("tokens_in", 0) or 0),
        "tokens": int(p.get("tokens_in", 0) or 0) + int(p.get("tokens_out", 0) or 0),
        "usd": float(p.get("usd_estimate", 0) or 0),
        # Eval fields (present only on eval.scored events; None otherwise).
        "eval_id": p.get("eval_id"),
        "eval_dimension": p.get("dimension") if e.event_type == "eval.scored" else None,
        "eval_target": p.get("target") if e.event_type == "eval.scored" else None,
        "eval_score": float(p["score"]) if e.event_type == "eval.scored" and "score" in p else None,
        "eval_passed": bool(p["passed"]) if e.event_type == "eval.scored" and "passed" in p else None,
    }


def _agg_evals(rows: list[dict], key: str) -> dict:
    """Group eval.scored rows by `key` -> {n, avg_score, pass_rate}."""
    groups: dict[str, dict] = {}
    for r in rows:
        k = r.get(key)
        if k is None:
            continue
        g = groups.setdefault(k, {"n": 0, "_sum": 0.0, "_passed": 0})
        g["n"] += 1
        g["_sum"] += float(r["eval_score"])
        g["_passed"] += 1 if r.get("eval_passed") else 0
    out = {}
    for k, g in groups.items():
        n = g["n"]
        out[k] = {"n": n, "avg_score": round(g["_sum"] / n, 4), "pass_rate": round(g["_passed"] / n, 4)}
    return out


# Event types worth surfacing verbatim in a work narrative (milestones).
_NOTABLE = {
    "gate.resolved", "decision.recorded", "override.invoked",
    "deploy.requested", "deploy.succeeded", "deploy.blocked",
    "phase.transition", "party.consensus_reached", "strike.recorded",
    "test.failed", "night_shift.completed", "night_shift.verdict", "night_shift.aborted",
}


def summarize_work(rows: list[dict]) -> dict:
    """Aggregate flattened event rows into a work summary: who did what (human vs
    agent vs system), by event type, by agent, totals, and notable milestones.
    Shared by the in-memory + Postgres stores so both produce the same shape."""
    by_actor_type: dict[str, int] = {"human": 0, "agent": 0, "system": 0}
    by_event_type: dict[str, int] = {}
    by_agent: dict[str, dict] = {}
    tokens = 0
    usd = 0.0
    for r in rows:
        at = r.get("actor_type") or "agent"
        by_actor_type[at] = by_actor_type.get(at, 0) + 1
        et = r["event_type"]
        by_event_type[et] = by_event_type.get(et, 0) + 1
        tokens += int(r.get("tokens", 0) or 0)
        usd += float(r.get("usd", 0) or 0)
        persona = r.get("agent_persona")
        if persona:
            g = by_agent.setdefault(persona, {"events": 0, "tokens": 0})
            g["events"] += 1
            g["tokens"] += int(r.get("tokens", 0) or 0)
    notable = sorted(
        (
            {"ts": r["ts"], "event_type": r["event_type"], "actor": r.get("actor"),
             "actor_type": r.get("actor_type"), "roadmap_id": r.get("roadmap_id")}
            for r in rows if r["event_type"] in _NOTABLE
        ),
        key=lambda x: x["ts"],
    )
    return {
        "total_events": len(rows),
        "by_actor_type": by_actor_type,
        "by_event_type": dict(sorted(by_event_type.items(), key=lambda kv: kv[1], reverse=True)),
        "by_agent": dict(sorted(by_agent.items(), key=lambda kv: kv[1]["events"], reverse=True)),
        "tokens": tokens,
        "usd": round(usd, 6),
        "notable": notable[:100],
    }


def context_usage_from(rows: list[dict]) -> dict:
    """From `llm.tokens_spent` rows: how close prompts came to the model's context
    window. Each agent call is a discrete prompt, so the meaningful gauge is the
    PEAK single-prompt tokens vs the window (plus the latest call + cumulative)."""
    from ..llm.context_windows import context_window_for

    if not rows:
        return {"model_id": None, "context_window": context_window_for(None),
                "peak_prompt_tokens": 0, "last_prompt_tokens": 0, "cumulative_tokens": 0,
                "pct_used": 0.0, "near_limit": False, "calls": 0}
    rows_sorted = sorted(rows, key=lambda r: r["ts"])
    last = rows_sorted[-1]
    peak = max(int(r.get("tokens_in", 0) or 0) for r in rows_sorted)
    model_id = last.get("model_id")
    window = context_window_for(model_id)
    pct = round(peak / window, 4) if window else 0.0
    return {
        "model_id": model_id,
        "context_window": window,
        "peak_prompt_tokens": peak,
        "last_prompt_tokens": int(last.get("tokens_in", 0) or 0),
        "cumulative_tokens": sum(int(r.get("tokens", 0) or 0) for r in rows_sorted),
        "pct_used": pct,
        "near_limit": pct >= 0.8,
        "calls": len(rows_sorted),
    }


def _require_org(org_id: str | None) -> str:
    if not org_id:
        # Cross-org analytics are banned (plan §5.3). Surface as a hard error
        # the admin route turns into a 400.
        raise ValueError("org_id is required — cross-org analytics are not permitted")
    return str(org_id)


class AnalyticsStore(Protocol):
    def ingest(self, batch: list[EventEnvelope]) -> None: ...
    def rollup(self, *, org_id, dimension, frm=None, to=None) -> list[dict]: ...
    def feature_timeline(self, *, org_id, roadmap_id) -> list[dict]: ...
    def live(self, *, org_id, limit=50) -> list[dict]: ...
    def totals(self, *, org_id) -> dict: ...
    def eval_summary(self, *, org_id) -> dict: ...
    def work_summary(self, *, org_id, frm=None, to=None, project_id=None) -> dict: ...
    def context_usage(self, *, org_id, project_id=None) -> dict: ...


class InMemoryAnalyticsStore:
    def __init__(self) -> None:
        self._events: list[dict] = []
        self._seen: set[str] = set()

    # write(batch) so the store doubles as a clickstream sink.
    def write(self, batch: list[EventEnvelope]) -> None:
        self.ingest(batch)

    def ingest(self, batch: list[EventEnvelope]) -> None:
        # Dedup on event_id so migration backfill (deterministic ids) is
        # idempotent — re-running writes nothing new (plan §12).
        for e in batch:
            eid = str(e.event_id)
            if eid in self._seen:
                continue
            self._seen.add(eid)
            self._events.append(_flatten(e))

    def _scope(self, org_id: str, frm: str | None, to: str | None) -> list[dict]:
        rows = [e for e in self._events if e["org_id"] == org_id]
        if frm:
            rows = [e for e in rows if e["ts"] >= frm]
        if to:
            rows = [e for e in rows if e["ts"] <= to]
        return rows

    def rollup(self, *, org_id, dimension, frm=None, to=None) -> list[dict]:
        org_id = _require_org(org_id)
        if dimension not in _DIMENSIONS:
            raise ValueError(f"unknown dimension {dimension!r}; valid: {sorted(_DIMENSIONS)}")
        field = _DIMENSIONS[dimension]
        groups: dict[str, dict] = {}
        for e in self._scope(org_id, frm, to):
            keys = e["domains"] if field == "domains" else [e.get(field)]
            for key in keys:
                if key is None:
                    continue
                g = groups.setdefault(key, {"key": key, "events": 0, "tokens": 0, "usd": 0.0})
                g["events"] += 1
                g["tokens"] += e["tokens"]
                g["usd"] = round(g["usd"] + e["usd"], 6)
        return sorted(groups.values(), key=lambda g: g["events"], reverse=True)

    def feature_timeline(self, *, org_id, roadmap_id) -> list[dict]:
        org_id = _require_org(org_id)
        rows = [e for e in self._scope(org_id, None, None) if e["roadmap_id"] == roadmap_id]
        return sorted(rows, key=lambda e: e["ts"])

    def live(self, *, org_id, limit=50) -> list[dict]:
        org_id = _require_org(org_id)
        return self._scope(org_id, None, None)[-limit:][::-1]

    def eval_summary(self, *, org_id) -> dict:
        org_id = _require_org(org_id)
        rows = [e for e in self._scope(org_id, None, None)
                if e["event_type"] == "eval.scored" and e.get("eval_score") is not None]
        return {"by_eval": _agg_evals(rows, "eval_id"), "by_agent": _agg_evals(rows, "eval_target")}

    def totals(self, *, org_id) -> dict:
        org_id = _require_org(org_id)
        rows = self._scope(org_id, None, None)
        return {
            "events": len(rows),
            "tokens": sum(e["tokens"] for e in rows),
            "usd": round(sum(e["usd"] for e in rows), 6),
        }

    def work_summary(self, *, org_id, frm=None, to=None, project_id=None) -> dict:
        org_id = _require_org(org_id)
        rows = self._scope(org_id, frm, to)
        if project_id:
            rows = [r for r in rows if r["project_id"] == str(project_id)]
        return {
            "window": {"from": frm, "to": to},
            "project_id": str(project_id) if project_id else None,
            **summarize_work(rows),
        }

    def context_usage(self, *, org_id, project_id=None) -> dict:
        org_id = _require_org(org_id)
        rows = [r for r in self._scope(org_id, None, None) if r["event_type"] == "llm.tokens_spent"]
        if project_id:
            rows = [r for r in rows if r["project_id"] == str(project_id)]
        return context_usage_from(rows)


_store: AnalyticsStore = InMemoryAnalyticsStore()


def set_analytics_store(store: AnalyticsStore) -> None:
    global _store
    _store = store


def reset_analytics_store() -> None:
    global _store
    _store = InMemoryAnalyticsStore()


def get_analytics_store() -> AnalyticsStore:
    return _store
