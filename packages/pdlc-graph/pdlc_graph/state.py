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
    # Feature-level traceability — ride on every event for admin drill-down.
    roadmap_id: str | None  # F-NNN
    prd_id: str | None
    user_story_id: str | None  # US-001
    plan_step: str | None

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
    # Night-shift runtime (Phase F)
    target_environment: str | None  # contracted deploy target (must be non-prod)
    night_shift_contract_accepted: bool  # the one human gate
    night_shift_last_verdict: dict  # latest Sentinel verdict (drives loop routing)
    night_shift_progress_log: list[str]  # progress fingerprints per Sentinel firing (stagnation guard)
    night_shift_outcome: str | None  # "completed" | "aborted" | "declined"
    night_shift_abort_reason: str | None
    ns_markers: list[str]  # test hook: inject ns-progress:/ns-abort: markers

    # Interaction mode (Constitution §8)
    interaction_mode: Literal["sketch", "socratic"]

    # Conversation buffer — kept small via summarization middleware
    messages: list[dict]

    # Correlation for instrumentation
    correlation_id: str | None

    # ── Inception (Phase B) working state ───────────────────────────────
    # Initialization (genesis: constitution + intent + roadmap seed)
    project_name: str | None
    init_answers: dict  # {round_title: [answers]} gathered by the init flow
    constitution_ref: str | None  # artifact uri of CONSTITUTION.md
    intent_ref: str | None  # artifact uri of INTENT.md
    roadmap_ref: str | None  # artifact uri of ROADMAP.md
    init_approved: bool  # init_approve gate verdict (gate #1)
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

    # ── Operation (Phase D) working state ───────────────────────────────
    commits: list[str]  # conventional-commit subjects driving the semver bump
    version: str | None  # semver tag chosen at Ship (e.g. "v1.3.0")
    changelog_ref: str | None  # artifact uri of the rendered CHANGELOG entry
    deploy_candidates: list[str]  # candidate environment names (prod filtered out)
    deploy_target: str | None  # selected environment name
    deploy_tier: str | None  # dev | test | staging | pre-production | production
    deploy_url: str | None
    merged: bool  # merge-to-main executed (--no-ff)
    merge_and_deploy_approved: bool  # gate #6 verdict
    deployments_ref: str | None  # artifact uri of the DEPLOYMENTS.md record
    smoke_results: dict  # {check: {"passed": bool, "report": str}}
    smoke_signed_off: bool  # gate #7 verdict
    simulate_failing_smoke: list[str]  # test hook: force these smoke checks to fail
    episode_ref: str | None  # artifact uri of the episode file
    episode_approved: bool  # gate #8 verdict
    metrics_ref: str | None  # artifact uri of the METRICS rollup
    operation_complete: bool

    # ── Utilities (Phase E) ─────────────────────────────────────────────
    utility_command: str | None  # set by the engine → meta routes to the utility subgraph
    utility_args: dict  # per-command inputs (e.g. {"title","rationale","scenario","reason"})
    utility_result: dict  # per-command summary the UI/engine surfaces
    paused: bool  # /pause … /resume
    abandoned: bool  # /abandon
    decisions: list[dict]  # /decide — the Decision Registry
    decisions_ref: str | None  # rendered DECISIONS.md artifact
    override_log: list[dict]  # /override — Tier-1 override audit trail
    doctor_report: dict | None  # /doctor — health-check findings
    doctor_ref: str | None
    whatif_ref: str | None  # /whatif — hypothetical analysis (read-only)
    rollback_ref: str | None  # /rollback — revert record
    hotfix_ref: str | None  # /hotfix — compressed build→ship record
