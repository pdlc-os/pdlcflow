"""PDLCState — the LangGraph state schema.

Mirrors the 12 sections of upstream pdlc's templates/STATE.md so the resume
contract survives the migration. Adds tenancy / taxonomy keys that ride on
every event for admin-dashboard rollups (initiative, application, repository,
domain).
"""

from __future__ import annotations

from typing import Literal, TypedDict


class ContextCheckpoint(TypedDict, total=False):
    triggered_at: str | None
    active_task: str | None
    sub_phase: str | None
    step: str | None
    skill_file: str | None
    work_in_progress: str | None
    next_action: str | None
    files_open: list[str]


class Handoff(TypedDict, total=False):
    phase_completed: str | None
    next_phase: str | None
    feature: str | None
    key_outputs: list[str]
    decisions_made: list[str]
    next_action: str | None
    pending_questions: list[str]


class RoadmapClaim(TypedDict, total=False):
    feature_id: str
    beads_task: str
    claimed_by: str
    claimed_at: str
    branch: str | None


class PDLCState(TypedDict, total=False):
    # Tenancy + taxonomy — ride on every event envelope
    org_id: str
    squad_id: str | None
    initiative_id: str | None
    application_id: str | None
    project_id: str
    repository: str | None
    domains: list[str]

    # Session
    session_id: str
    thread_id: str
    actor: str

    # STATE.md mirror (12 sections)
    phase: Literal["Initialization", "Inception", "Construction", "Operation"]
    feature: str | None
    active_beads_task: str | None  # preserved external_id ("bd-NN") for migration
    roadmap_claim: RoadmapClaim | None
    sub_phase: str | None
    last_checkpoint: str | None
    party_mode: Literal["agent-teams", "subagents", "solo", "none"]
    active_blockers: list[dict]
    context_checkpoint: ContextCheckpoint
    handoff: Handoff
    phase_history: list[dict]

    # Night-shift overlay
    night_shift_active: bool
    night_shift_run_id: str | None

    # Interaction mode (Constitution §8)
    interaction_mode: Literal["sketch", "socratic"]

    # Conversation buffer — kept small via summarization middleware
    messages: list[dict]

    # Correlation for instrumentation
    correlation_id: str | None
