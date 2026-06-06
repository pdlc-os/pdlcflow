"""Typed payload models — one per event type in `EVENT_TYPES`.

These are validated by the emitter via `model_validate` on the appropriate
class for the given event_type. Payloads carry references (S3 keys, IDs)
rather than content. See registry.md for the per-event semantics.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------- Session ----------------
class SessionOpenedPayload(_P):
    interaction_mode: Literal["sketch", "socratic"] = "socratic"


class SessionResumedPayload(_P):
    last_checkpoint: str | None = None
    sub_phase: str | None = None


class SessionClosedPayload(_P):
    duration_ms: int


# ---------------- Phase / sub-phase / step ----------------
class PhaseEnteredPayload(_P):
    phase: Literal["Initialization", "Inception", "Construction", "Operation"]


class PhaseExitedPayload(_P):
    phase: Literal["Initialization", "Inception", "Construction", "Operation"]
    duration_ms: int


class PhaseTransitionPayload(_P):
    from_phase: str
    to_phase: str


class SubphaseEnteredPayload(_P):
    sub_phase: str


class SubphaseExitedPayload(_P):
    sub_phase: str
    duration_ms: int


class StepCompletedPayload(_P):
    skill: str
    step: str  # e.g. "Step 7"
    skill_file: str
    work_in_progress: str | None = None


# ---------------- Skill / agent ----------------
class SkillInvokedPayload(_P):
    skill: str
    args: list[str] = []


class AgentInvokedPayload(_P):
    agent_persona: str
    tier: Literal["opus", "sonnet", "haiku"]
    purpose: str


class AgentRespondedPayload(_P):
    agent_persona: str
    duration_ms: int
    tool_calls: int = 0
    finish_reason: str | None = None


# ---------------- Approval gates ----------------
class GateOpenedPayload(_P):
    gate_kind: str
    artifact_uri: str | None = None
    summary: list[str] = []


class GateResolvedPayload(_P):
    gate_kind: str
    status: Literal["approved", "rejected", "edited", "expired"]
    comment_ref: str | None = None  # S3 key, not the text


# ---------------- Party meetings ----------------
class PartyOpenedPayload(_P):
    party_kind: Literal[
        "wave_kickoff", "design_roundtable", "party_review", "strike_panel"
    ]
    roster: list[str]
    topic_ref: str | None = None


class PartyPitchReceivedPayload(_P):
    party_kind: str
    persona: str
    duration_ms: int
    pitch_ref: str  # S3 key for the full pitch markdown


class PartyConsensusReachedPayload(_P):
    party_kind: str
    decision: str
    mom_ref: str  # S3 key for the MOM artifact
    auto: bool = False  # true under /night-shift


# ---------------- Tools ----------------
class ToolInvokedPayload(_P):
    tool: str
    args_summary: str | None = None  # short, no payload content


class ToolBlockedPayload(_P):
    tool: str
    rule: str
    advice: str | None = None


# ---------------- Tests ----------------
class TestRunPayload(_P):
    layer: Literal[
        "unit", "integration", "contract", "e2e",
        "security", "perf", "ux",
    ]
    target: str


class TestPassedPayload(_P):
    layer: str
    target: str
    duration_ms: int


class TestFailedPayload(_P):
    layer: str
    target: str
    failure_ref: str  # S3 key for the test report
    duration_ms: int


# ---------------- Strikes ----------------
class StrikeRecordedPayload(_P):
    attempt: int
    failing_test: str


class StrikePanelConvenedPayload(_P):
    failing_test: str
    panel_roster: list[str]


# ---------------- Deploy ----------------
class DeployRequestedPayload(_P):
    environment: str
    tier: Literal["dev", "test", "staging", "pre-production", "non-production", "production"]
    command_summary: str


class DeploySucceededPayload(_P):
    environment: str
    tier: str
    duration_ms: int
    url: str | None = None


class DeployBlockedPayload(_P):
    environment: str
    tier: str
    rule: str


# ---------------- Night-shift ----------------
class NightShiftStartedPayload(_P):
    run_id: str
    feature_id: str
    wall_clock_cap_s: int
    token_cap: int


class NightShiftVerdictPayload(_P):
    run_id: str
    verdict: Literal["continue", "complete", "abort"]
    reason: str | None = None


class NightShiftCompletedPayload(_P):
    run_id: str
    duration_ms: int
    auto_decisions: int


class NightShiftAbortedPayload(_P):
    run_id: str
    reason: str


# ---------------- Decision / override ----------------
class DecisionRecordedPayload(_P):
    decision_id: str
    title: str
    rationale_ref: str  # S3 key


class OverrideInvokedPayload(_P):
    rule: str
    justification_ref: str


# ---------------- LLM ----------------
class LLMTokensSpentPayload(_P):
    provider: Literal[
        "bedrock", "anthropic", "vertex", "azure",
        "openai", "gemini", "ollama",
    ]
    model_id: str
    tier: Literal["opus", "sonnet", "haiku"]
    agent_persona: str
    tokens_in: int
    tokens_out: int
    usd_estimate: float | None = None


# ---------------- Context / UI / error ----------------
class ContextWarningPayload(_P):
    level: Literal["warning", "critical"]
    remaining_pct: int


class UIViewedPayload(_P):
    route: str
    component: str | None = None


class ErrorPayload(_P):
    exc_type: str
    where: str  # node / route name; never a stack trace with paths


# ---------------- Evaluation (Phase J) ----------------
class EvalScoredPayload(_P):
    eval_id: str
    kind: Literal["llm_judge", "deterministic"]
    dimension: str  # quality | groundedness | citation | faithful_relay | drift
    target: str  # agent persona or step id being evaluated
    trigger: str  # the step that produced the output (prd, design_docs, plan, review, ...)
    score: float  # 0.0–1.0
    passed: bool
    threshold: float
    blocking: bool
    rationale: str = ""


class EvalBlockedPayload(_P):
    eval_id: str
    gate: str  # the approval gate that was blocked
    dimension: str
    score: float
    threshold: float
    reason: str = ""
