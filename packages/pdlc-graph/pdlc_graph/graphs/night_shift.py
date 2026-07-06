"""Night-shift subgraph — autonomous Build → Ship under Sentinel supervision.

State machine (plan §10):

    preflight → contract_party → activate → build → sentinel → ship → sentinel
                    │ (decline)                         │ (abort)        │ (abort)
                    ▼                                    ▼                ▼
                 declined                             aborted ◄──────────┘
                                                                  complete ▶ completed

The Contract Party is the ONE human gate (a raw `interrupt()`, NOT
`gates.approval_gate` — so it always pauses even though `night_shift_active` is
set; every gate *inside* build/ship auto-approves). The Sentinel fires on the
internal edges, reading `ns-progress:`/`ns-abort:` markers synthesized from
state, and routes continue / complete / abort. The three-layer prod-deploy ban
holds: candidates are pre-filtered (Ship), the contract refuses a production
target, and the Sentinel aborts on `prod-deploy-attempted`.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ..deploy_port import infer_tier
from ..instrumentation import emit_event, instrumented_node
from ..sentinel.evaluator import evaluate
from ..state import PDLCState
from .build import build_graph
from .ship import ship_graph


def _state_md(state: PDLCState) -> str:
    """Synthesize the Sentinel marker document from run state."""
    parts: list[str] = list(state.get("ns_markers") or [])
    if state.get("construction_complete"):
        parts.append("ns-progress:build-done")
    if state.get("operation_complete"):
        parts.append("ns-progress:complete")
    for _check, result in (state.get("smoke_results") or {}).items():
        if result.get("required") and not result.get("passed"):
            parts.append("ns-abort:smoke-failed")
    return "\n".join(parts)


# ── nodes ──────────────────────────────────────────────────────────────────
@instrumented_node("night_shift.started")
def preflight(state: PDLCState) -> dict:
    """Validate the run can start autonomously (Inception complete, target safe)."""
    if not state.get("feature"):
        return {"night_shift_abort_reason": "preflight: no feature"}
    if not state.get("tasks"):
        return {"night_shift_abort_reason": "preflight: no tasks (run Inception first)"}
    target = state.get("target_environment")
    if target and infer_tier(target) == "production":
        return {"night_shift_abort_reason": "preflight: production target is not permitted"}
    return {"night_shift_abort_reason": None}


@instrumented_node("night_shift.started")
def contract_party(state: PDLCState) -> dict:
    """The single human gate. A raw interrupt so it never auto-approves."""
    decision = interrupt(
        {
            "kind": "approval",
            "gate": "night_shift_contract",
            "feature": state.get("feature"),
            "target_environment": state.get("target_environment"),
            "summary": (
                "Autonomous Build → Ship. The Contract Party is the only human "
                "checkpoint; all downstream gates auto-resolve under the Sentinel."
            ),
        }
    )
    accepted = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    return {"night_shift_contract_accepted": accepted}


@instrumented_node("night_shift.started")
def activate(state: PDLCState) -> dict:
    return {
        "night_shift_active": True,
        "night_shift_run_id": state.get("night_shift_run_id") or f"ns-{state.get('feature', 'run')}",
        "phase": "Construction",
    }


def _fingerprint(state: PDLCState) -> str:
    """A monotonic-ish progress signature for stagnation detection."""
    import re

    markers = sorted(set(re.findall(r"ns-progress:([a-z0-9-]+)", _state_md(state))))
    return "|".join(markers)


def _sentinel(state: PDLCState, stage: str) -> dict:
    # Append this firing's progress fingerprint (replay-safe: it rides the
    # returned state delta), then evaluate against the updated log so the
    # stagnation guard can compare across firings.
    log = [*(state.get("night_shift_progress_log") or []), _fingerprint(state)]
    verdict = evaluate({**state, "night_shift_progress_log": log}, _state_md(state))
    emit_event("night_shift.verdict", state, {"stage": stage, **verdict})
    return {"night_shift_progress_log": log, "night_shift_last_verdict": verdict}


@instrumented_node("step.completed")
def sentinel_after_build(state: PDLCState) -> dict:
    return _sentinel(state, "build")


@instrumented_node("step.completed")
def sentinel_after_ship(state: PDLCState) -> dict:
    return _sentinel(state, "ship")


@instrumented_node("night_shift.completed")
def completed(state: PDLCState) -> dict:
    return {"night_shift_outcome": "completed", "night_shift_active": False}


@instrumented_node("night_shift.aborted")
def aborted(state: PDLCState) -> dict:
    verdict = state.get("night_shift_last_verdict") or {}
    reason = state.get("night_shift_abort_reason") or verdict.get("reason") or "aborted"
    return {
        "night_shift_outcome": "aborted",
        "night_shift_abort_reason": reason,
        "night_shift_active": False,
    }


@instrumented_node("night_shift.aborted")
def declined(state: PDLCState) -> dict:
    return {"night_shift_outcome": "declined", "night_shift_active": False}


# ── routers ────────────────────────────────────────────────────────────────
def _after_preflight(state: PDLCState) -> str:
    return "aborted" if state.get("night_shift_abort_reason") else "contract_party"


def _after_contract(state: PDLCState) -> str:
    return "activate" if state.get("night_shift_contract_accepted") else "declined"


def _after_build(state: PDLCState) -> str:
    return "aborted" if state.get("night_shift_last_verdict", {}).get("verdict") == "abort" else "ship"


def _after_ship(state: PDLCState) -> str:
    return "aborted" if state.get("night_shift_last_verdict", {}).get("verdict") == "abort" else "completed"


def build_night_shift(checkpointer=None):
    """Compile the night-shift graph. Pass a checkpointer (MemorySaver /
    PostgresSaver) so the Contract Party interrupt is resumable."""
    g = StateGraph(PDLCState)
    g.add_node("preflight", preflight)
    g.add_node("contract_party", contract_party)
    g.add_node("activate", activate)
    g.add_node("build", build_graph)
    g.add_node("sentinel_after_build", sentinel_after_build)
    g.add_node("ship", ship_graph)
    g.add_node("sentinel_after_ship", sentinel_after_ship)
    g.add_node("completed", completed)
    g.add_node("aborted", aborted)
    g.add_node("declined", declined)

    g.add_edge(START, "preflight")
    g.add_conditional_edges("preflight", _after_preflight, ["contract_party", "aborted"])
    g.add_conditional_edges("contract_party", _after_contract, ["activate", "declined"])
    g.add_edge("activate", "build")
    g.add_edge("build", "sentinel_after_build")
    g.add_conditional_edges("sentinel_after_build", _after_build, ["ship", "aborted"])
    g.add_edge("ship", "sentinel_after_ship")
    g.add_conditional_edges("sentinel_after_ship", _after_ship, ["completed", "aborted"])
    for terminal in ("completed", "aborted", "declined"):
        g.add_edge(terminal, END)
    return g.compile(checkpointer=checkpointer)


night_shift_graph = build_night_shift()
