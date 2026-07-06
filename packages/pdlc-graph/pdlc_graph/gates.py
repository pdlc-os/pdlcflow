"""Approval gates — the 8 human checkpoints as `interrupt()` sites.

This module owns the 4 Inception gates (Discover / Define / Design / Plan);
Construction and Operation reuse the same `approval_gate` helper in later
phases. Each gate emits one typed payload the engine turns into an
`<ApprovalGateModal>`; the human's verdict resumes the graph.

Under `/night-shift` the gate does NOT block — it calls the auto-decision
matrix (Phase F) and records the auto-pick. Phase B ships a conservative
default matrix (approve unless the payload flags a hard blocker) so the
night-shift path is exercisable end-to-end now.
"""

from __future__ import annotations

from langgraph.types import interrupt

from .state import PDLCState

# The 9 canonical gate kinds (plan §2.4). Initialization owns the first;
# Inception owns the next four.
GATE_KINDS = (
    "init_approve",
    "discover_summary",
    "prd_approve",
    "design_docs_approve",
    "beads_tasklist_approve",
    "review_md_approve",
    "merge_and_deploy_approve",
    "smoke_signoff",
    "episode_approve",
)


def _auto_decision(gate_kind: str, payload: dict) -> dict:
    """Night-shift auto-pick. Hard blockers (e.g. unresolved P0 UX finding)
    refuse; everything else is approved and logged."""
    if payload.get("blocking"):
        return {
            "approved": False,
            "auto": True,
            "comment": f"night-shift refused {gate_kind}: {payload['blocking']}",
        }
    return {"approved": True, "auto": True, "comment": f"night-shift auto-approved {gate_kind}"}


def approval_gate(state: PDLCState, gate_kind: str, payload: dict) -> dict:
    """Open an approval gate. Returns the verdict dict
    {"approved": bool, "comment": str|None, "edit": dict|None, "auto"?: bool}.
    """
    if gate_kind not in GATE_KINDS:
        raise ValueError(f"unknown gate kind {gate_kind!r}; valid: {GATE_KINDS}")

    full = {"kind": "approval", "gate": gate_kind, **payload}

    if state.get("night_shift_active"):
        return _auto_decision(gate_kind, payload)

    verdict = interrupt(full)
    if isinstance(verdict, bool):
        return {"approved": verdict}
    return verdict
