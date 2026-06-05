"""Sketch vs Socratic question delivery (upstream skills/interaction-mode.md).

Both modes cover identical depth; they differ only in cadence:

- **Socratic** — one open question at a time, user answers from scratch.
- **Sketch**  — agent drafts answers from context, batches a round, user edits.

A node calls `ask(state, questions, drafts=...)`. The function emits a single
`interrupt()` carrying the mode + questions (+ drafts in Sketch mode); the
human's resume payload is returned as `{"answers": [...]}`. Under
`/night-shift` the graph never blocks — Sketch drafts are auto-accepted.
"""

from __future__ import annotations

from langgraph.types import interrupt

from .state import PDLCState

Mode = str  # "sketch" | "socratic"


def current_mode(state: PDLCState) -> Mode:
    return state.get("interaction_mode", "sketch")


def ask(
    state: PDLCState,
    questions: list[str],
    *,
    drafts: list[str] | None = None,
    context: str | None = None,
    visual: dict | None = None,
) -> dict:
    """Ask the human a round of questions. Returns {"answers": [...], ...}.

    In Sketch mode `drafts` (agent-proposed answers, one per question) are
    surfaced for edit. `visual` is an optional companion spec (see
    `pdlc_graph.visual`) the Studio panel renders beside the question. Under
    night-shift the drafts are auto-accepted with no human turn (falls back to
    empty strings when no drafts were supplied).
    """
    mode = current_mode(state)
    payload = {
        "kind": "user_input_required",
        "mode": mode,
        "questions": questions,
        "drafts": drafts if (mode == "sketch" and drafts) else None,
        "context": context,
        "visual": visual,
    }

    if state.get("night_shift_active"):
        answers = list(drafts) if drafts else ["" for _ in questions]
        return {"answers": answers, "auto": True}

    result = interrupt(payload)
    # Resume payloads may arrive as a bare list or the canonical dict.
    if isinstance(result, list):
        return {"answers": result}
    return result
