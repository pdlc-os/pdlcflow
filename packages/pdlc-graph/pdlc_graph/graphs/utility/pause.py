"""/pause — cleanly pause the active feature, saving a recovery checkpoint.

Faithful (but bounded + hermetic) port of upstream `skills/pause`: it sets the
`paused` flag, records a checkpoint note describing where work stopped, and
leaves all artifacts intact so `/resume` can pick up exactly where it left off.

Pure node: no interrupt, no git, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ...instrumentation import instrumented_node
from ...state import PDLCState


@instrumented_node("skill.invoked")
def pause_node(state: PDLCState) -> dict:
    """Pause the current feature and record a checkpoint note."""
    feature = state.get("feature")
    phase = state.get("phase")
    sub_phase = state.get("sub_phase")
    paused_at = datetime.now(UTC).isoformat()

    checkpoint = f"Paused / {phase or 'unknown'} / {paused_at}"

    return {
        "paused": True,
        "last_checkpoint": checkpoint,
        "utility_result": {
            "command": "pause",
            "paused": True,
            "feature": feature,
            "phase": phase,
            "sub_phase": sub_phase,
            "checkpoint": checkpoint,
            "paused_at": paused_at,
            "note": (
                f"Feature {feature!r} paused at {phase or 'unknown'}"
                f" / {sub_phase or 'none'}. Artifacts preserved; run /resume to continue."
            ),
        },
    }
