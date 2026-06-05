"""Backfill historical events from decisions + phase history.

Each synthetic event carries ``payload.synthetic = True`` so admin dashboards
can distinguish live vs reconstructed activity. Re-running is idempotent: the
``event_id`` is a uuid5 derived from ``(event_type, ts, roadmap_id/title)``, so
the same upstream project always yields the identical event list and the engine
dedups on ``(org_id, event_id)`` — a second pass writes nothing new.
"""

from __future__ import annotations

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from event_schema.envelope import EVENT_TYPES

from .scan import parse_decisions, parse_phase_history, parse_roadmap

# Phase-history ``event`` column -> envelope event_type. Anything not listed
# here falls back by suffix: ``*_start`` -> phase.entered, else a sub-phase
# transition (subphase.entered).
_PHASE_EVENT_MAP: dict[str, str] = {
    "deploy_succeeded": "deploy.succeeded",
    "operation_complete": "session.closed",
}


def _event_id(event_type: str, ts: str, key: str | None) -> str:
    """Stable uuid5 (string) for idempotent re-import."""
    return str(uuid5(NAMESPACE_URL, f"{event_type}|{ts}|{key or ''}"))


def _classify(event: str) -> str:
    """Map a phase-history ``event`` label to an envelope event_type."""
    if event in _PHASE_EVENT_MAP:
        return _PHASE_EVENT_MAP[event]
    if event.endswith("_start"):
        return "phase.entered"
    return "subphase.entered"


def backfill_events(root: Path) -> list[dict]:
    """Synthesize the import contract's ``events`` array for ``root``.

    Sources:
      * ``STATE.md`` phase history — one event per row (phase.entered /
        subphase.entered / deploy.succeeded / session.closed).
      * ``DECISIONS.md`` — one ``decision.recorded`` event per decision.

    Output is deterministic: identical input always produces an identical list
    with identical ``event_id`` values.
    """
    feature_to_fid = parse_roadmap(root)
    events: list[dict] = []

    for row in parse_phase_history(root):
        event_type = _classify(row["event"])
        ts = row["ts"]
        feature = row.get("feature", "")
        roadmap_id = feature_to_fid.get(feature)
        events.append(
            {
                "event_id": _event_id(event_type, ts, roadmap_id or feature),
                "event_type": event_type,
                "ts": ts,
                "roadmap_id": roadmap_id,
                "user_story_id": None,
                "payload": {
                    "synthetic": True,
                    "source": "phase_history",
                    "raw_event": row["event"],
                    "phase": row["phase"],
                    "sub_phase": row["sub_phase"],
                },
            }
        )

    for dec in parse_decisions(root):
        event_type = "decision.recorded"
        ts = dec["date"]
        events.append(
            {
                "event_id": _event_id(event_type, ts, dec["id"]),
                "event_type": event_type,
                "ts": ts,
                "roadmap_id": None,
                "user_story_id": None,
                "payload": {
                    "synthetic": True,
                    "source": "decisions",
                    "decision_id": dec["id"],
                    "title": dec["title"],
                    "rationale": dec["rationale"],
                },
            }
        )

    # Defensive: never emit an event_type the envelope would reject.
    for ev in events:
        assert ev["event_type"] in EVENT_TYPES, ev["event_type"]

    return events
