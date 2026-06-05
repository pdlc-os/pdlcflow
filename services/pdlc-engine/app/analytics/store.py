"""Analytics read store — the query side of the clickstream.

The emitter feeds every event here (in addition to the durable sink); the Atlas
Console admin routes query it for rollups. In-memory by default so the whole
dashboard works hermetically in tests and single-process dev; the engine
injects a ClickHouse/Postgres-backed store at boot for SaaS/self-host.

Cross-org analytics are banned by design (plan §5.3): every query REQUIRES an
`org_id` and only ever scans that org's events.
"""

from __future__ import annotations

from typing import Protocol

from event_schema import EventEnvelope

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
        "agent_persona": p.get("agent_persona"),
        "tokens": int(p.get("tokens_in", 0) or 0) + int(p.get("tokens_out", 0) or 0),
        "usd": float(p.get("usd_estimate", 0) or 0),
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


class InMemoryAnalyticsStore:
    def __init__(self) -> None:
        self._events: list[dict] = []

    # write(batch) so the store doubles as a clickstream sink.
    def write(self, batch: list[EventEnvelope]) -> None:
        self.ingest(batch)

    def ingest(self, batch: list[EventEnvelope]) -> None:
        for e in batch:
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

    def totals(self, *, org_id) -> dict:
        org_id = _require_org(org_id)
        rows = self._scope(org_id, None, None)
        return {
            "events": len(rows),
            "tokens": sum(e["tokens"] for e in rows),
            "usd": round(sum(e["usd"] for e in rows), 6),
        }


_store: AnalyticsStore = InMemoryAnalyticsStore()


def set_analytics_store(store: AnalyticsStore) -> None:
    global _store
    _store = store


def reset_analytics_store() -> None:
    global _store
    _store = InMemoryAnalyticsStore()


def get_analytics_store() -> AnalyticsStore:
    return _store
