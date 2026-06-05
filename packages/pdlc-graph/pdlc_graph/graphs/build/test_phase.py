"""Construction Test sub-phase + wrap-up (upstream steps 04-test / 05-wrap-up).

Runs the 7 PDLC test layers through the injectable test-runner port, records
the results, then writes the Construction → Operation handoff. Required layers
(unit/integration/security) that fail pause for a human accept/fix/defer
decision unless night-shift is active.
"""

from __future__ import annotations

from langgraph.types import interrupt

from ...instrumentation import instrumented_node
from ...state import PDLCState
from ...test_runner_port import run_layer

# The 7 PDLC layers; required ones gate the phase (plan §, upstream CONSTITUTION §7).
_LAYERS = [
    ("unit", True),
    ("integration", True),
    ("contract", False),
    ("e2e", False),
    ("security", True),
    ("perf", False),
    ("ux", False),
]


@instrumented_node("subphase.entered")
def test_phase(state: PDLCState) -> dict:
    """Step 15-17 — run every layer; pause on a required-layer failure."""
    feature = state.get("feature") or "untitled-feature"
    fail_layers = set(state.get("simulate_failing_layers") or [])  # test hook

    results: dict[str, dict] = {}
    failed_required: list[str] = []
    for layer, required in _LAYERS:
        res = run_layer(layer, feature, attempt=0, fail_until=1 if layer in fail_layers else 0)
        results[layer] = {"passed": res["passed"], "required": required, "report": res["report"]}
        if required and not res["passed"]:
            failed_required.append(layer)

    if failed_required and not state.get("night_shift_active"):
        # Human decides accept / fix / defer (upstream Step 17). Resume value is
        # ignored for record-keeping here; the decision is captured downstream.
        interrupt(
            {
                "kind": "user_input_required",
                "mode": "test_failures",
                "questions": [
                    f"Required test layers failed: {', '.join(failed_required)}. "
                    "Accept / fix / defer?"
                ],
                "failed_layers": failed_required,
            }
        )

    return {"construction_test_results": results}


@instrumented_node("subphase.exited")
def wrap_up(state: PDLCState) -> dict:
    """Step 18-20 — Construction complete; hand off to Operation."""
    feature = state.get("feature")
    build_log = state.get("build_log") or []
    handoff = {
        "phase_completed": "Construction",
        "next_phase": "Operation / Ship",
        "feature": feature,
        "key_outputs": [ref for ref in (state.get("review_ref"),) if ref],
        "decisions_made": [f"{len(build_log)} tasks built and reviewed"],
        "next_action": "Start Operation — run /ship",
        "pending_questions": [],
    }
    return {"sub_phase": "Test", "construction_complete": True, "handoff": handoff}
