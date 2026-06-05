"""/resume — resume a paused feature from its saved checkpoint.

Faithful (but bounded + hermetic) port of upstream `skills/resume`: it clears
the `paused` flag and reports the feature being resumed and the checkpoint it
picks up from. No git rebase, no Beads reclaim, no network here.

Pure node: no interrupt.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ...instrumentation import instrumented_node
from ...state import PDLCState


@instrumented_node("skill.invoked")
def resume_node(state: PDLCState) -> dict:
    """Resume the paused feature, clearing the pause flag."""
    feature = state.get("feature")
    phase = state.get("phase")
    sub_phase = state.get("sub_phase")
    prior_checkpoint = state.get("last_checkpoint")
    resumed_at = datetime.now(UTC).isoformat()

    checkpoint = f"Resumed / {phase or 'unknown'} / {resumed_at}"

    return {
        "paused": False,
        "last_checkpoint": checkpoint,
        "utility_result": {
            "command": "resume",
            "paused": False,
            "resumed": True,
            "feature": feature,
            "phase": phase,
            "sub_phase": sub_phase,
            "from_checkpoint": prior_checkpoint,
            "checkpoint": checkpoint,
            "resumed_at": resumed_at,
            "note": (
                f"Feature {feature!r} resumed at {phase or 'unknown'}"
                f" / {sub_phase or 'none'}."
            ),
        },
    }
