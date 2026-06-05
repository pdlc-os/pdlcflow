"""/abandon — stop work on a feature that is no longer viable.

Faithful (but bounded + hermetic) port of upstream `skills/abandon`: it marks
the feature abandoned and releases its roadmap claim, but — per the foundation
contract — does NOT delete artifacts (PRD, design docs, build log remain for
the record / abandonment episode).

Pure node: no interrupt.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ...instrumentation import instrumented_node
from ...state import PDLCState


@instrumented_node("skill.invoked")
def abandon_node(state: PDLCState) -> dict:
    """Mark the feature abandoned and drop its roadmap claim."""
    args = state.get("utility_args") or {}
    feature = args.get("feature") or state.get("feature")
    reason = args.get("reason")
    phase = state.get("phase")
    sub_phase = state.get("sub_phase")
    abandoned_at = datetime.now(UTC).isoformat()

    return {
        "abandoned": True,
        "roadmap_claim": None,
        "utility_result": {
            "command": "abandon",
            "abandoned": True,
            "feature": feature,
            "reason": reason,
            "phase": phase,
            "sub_phase": sub_phase,
            "abandoned_at": abandoned_at,
            "artifacts_preserved": True,
            "note": (
                f"Feature {feature!r} abandoned at {phase or 'unknown'}"
                f" / {sub_phase or 'none'}. Artifacts preserved; roadmap claim released."
            ),
        },
    }
