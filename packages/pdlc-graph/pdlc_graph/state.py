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

    # ── Inception (Phase B) working state ───────────────────────────────
    # The brainstorm log accumulates one section per Discover/Design step.
    brainstorm_log: list[dict]  # [{"section": str, "body": str, "step": str}]
    discovery_summary: str | None
    # Define
    prd_ref: str | None  # artifact uri of the rendered PRD
    prd_approved: bool
    # Design
    design_dir: str | None
    design_docs: dict  # {"architecture": uri, "data_model": uri, "api_contracts": uri, ...}
    threat_model_ref: str | None
    ux_review_ref: str | None
    design_approved: bool
    # Plan
    plan_ref: str | None
    tasks: list[dict]  # [{"external_id": "bd-1", "title": ..., "labels": [...], "depends_on": [...]}]
    plan_approved: bool
    # Party-meeting results keyed by topic slug ("progressive-thinking", "threat-model", "design-laws")
    party_results: dict

    # ── Inception inputs / triage signals ──────────────────────────────
    # Declared so the StateGraph retains them (undeclared keys are dropped).
    enable_divergent_ideation: bool  # opt into Discover Step 0 (node name avoids key clash)
    visual: bool  # feature has a visual/UI surface — gates UX Discovery (Step 4.5)
    threat_signals: list[bool]  # Design threat-model triage checklist (skip/lite/full)
    ux_signals: list[bool]  # Design design-laws triage checklist (skip/lite/full)

    # ── Construction (Phase C) working state ────────────────────────────
    current_wave: int  # 1-based wave index being executed
    current_task_id: str | None  # external_id of the task in flight
    test_loop: dict  # {task_external_id: fix_attempts} — drives 3-Strike
    strike_history: list[dict]  # one record per Strike Panel convened
    build_log: list[dict]  # per-task build record (red/green/refactor + outcome)
    review_ref: str | None  # artifact uri of the rendered REVIEW.md
    review_approved: bool  # End-of-Review gate verdict (gate #5)
    construction_test_results: dict  # {layer: {"passed": bool, "report": str}}
    construction_complete: bool
    simulate_failing_layers: list[str]  # test hook: force these Test layers to fail
