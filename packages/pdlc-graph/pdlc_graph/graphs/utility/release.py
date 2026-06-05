"""/release — force-release a stuck roadmap-level feature claim (admin).

Faithful (but bounded + hermetic) port of upstream `skills/release`: it clears
a held roadmap claim so the feature returns to the ready queue. The held claim
that was released is read from prior state and surfaced in the result for the
audit trail. No Beads, no git, no network here.

Pure node: no interrupt.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ...instrumentation import instrumented_node
from ...state import PDLCState


@instrumented_node("skill.invoked")
def release_node(state: PDLCState) -> dict:
    """Force-release the currently-held roadmap claim."""
    args = state.get("utility_args") or {}
    reason = args.get("reason")
    held_claim = state.get("roadmap_claim")
    released_at = datetime.now(UTC).isoformat()

    feature_id = None
    if isinstance(held_claim, dict):
        feature_id = held_claim.get("feature_id")

    return {
        "roadmap_claim": None,
        "utility_result": {
            "command": "release",
            "released": True,
            "released_claim": held_claim,
            "feature_id": feature_id,
            "reason": reason,
            "released_at": released_at,
            "note": (
                f"Roadmap claim {feature_id or '(none held)'} force-released;"
                " feature available for the next /brainstorm."
                if held_claim
                else "No roadmap claim was held; nothing to release."
            ),
        },
    }
