"""Event envelope — the wire format for every clickstream emission.

Tenancy and taxonomy fields ride on every event so admin dashboards can pivot
rollups by initiative, application, repository, or domain without joining back
to entity tables for every query.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Forbidden PII keys are stripped pre-emission. Keep the list small and only
# add keys that we know we never want to ship — false positives are cheap to
# correct, false negatives leak.
_PII_KEYS: set[str] = {
    "prompt", "message", "content", "messages",
    "body", "raw_input", "raw_output", "completion",
}

EVENT_TYPES: set[str] = {
    # Session
    "session.opened", "session.resumed", "session.closed",
    # Phase
    "phase.entered", "phase.exited", "phase.transition",
    # Sub-phase
    "subphase.entered", "subphase.exited",
    # Step
    "step.completed",
    # Skill
    "skill.invoked",
    # Agent
    "agent.invoked", "agent.responded",
    # Approval gate
    "gate.opened", "gate.resolved",
    # Party
    "party.opened", "party.pitch_received", "party.consensus_reached",
    # Tool
    "tool.invoked", "tool.blocked",
    # Test
    "test.run", "test.passed", "test.failed",
    # Strike
    "strike.recorded", "strike.panel_convened",
    # Deploy
    "deploy.requested", "deploy.succeeded", "deploy.blocked",
    # Night-shift
    "night_shift.started", "night_shift.verdict",
    "night_shift.completed", "night_shift.aborted",
    # Decision / override
    "decision.recorded", "override.invoked",
    # LLM
    "llm.tokens_spent",
    # Context / UI / error
    "context.warning", "ui.viewed", "error",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EventEnvelope(BaseModel):
    """The single wire shape for every event. Payload is per-type and lives
    alongside in `payloads.py`. The envelope itself is provider-agnostic and
    sink-agnostic — emitter, Firehose, Postgres, JSONL, and ClickHouse all
    accept the same shape."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Identity / versioning
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    schema_version: int = 1
    ts: datetime = Field(default_factory=_utcnow)

    # Tenancy + taxonomy (every dim the admin dashboard pivots on)
    org_id: UUID
    squad_id: UUID | None = None
    initiative_id: UUID | None = None
    application_id: UUID | None = None
    project_id: UUID
    repository: str | None = None
    domains: list[str] = Field(default_factory=list)

    # Feature-level traceability — drill-down dimensions for rollups, so spend
    # and cycle time can be pivoted down to a roadmap item, PRD, user story, or
    # plan step (not just the application). Human-facing ids (F-NNN, US-001, …).
    roadmap_id: str | None = None
    prd_id: str | None = None
    user_story_id: str | None = None
    plan_step: str | None = None

    # Correlation
    session_id: str | None = None
    thread_id: str | None = None
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    actor: str | None = None

    # Typed payload (validated per event type by the emitter)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _known_event_type(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(
                f"unknown event_type {v!r}; "
                f"add to event_schema.envelope.EVENT_TYPES + registry.md"
            )
        return v

    @field_validator("payload")
    @classmethod
    def _strip_pii(cls, v: dict[str, Any]) -> dict[str, Any]:
        leaks = _PII_KEYS & v.keys()
        if leaks:
            raise ValueError(
                f"payload may not contain PII keys {sorted(leaks)}; "
                f"send references (S3 keys, IDs) instead"
            )
        return v
