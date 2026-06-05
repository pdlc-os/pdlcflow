"""Party-meeting orchestrator — one pattern serves all four party kinds.

Pattern: fan-out to N personas in parallel via Send, collect their pitches,
run a consensus node that produces a MOM artifact and a binding vote.

Under /night-shift, the consensus node auto-picks and logs to the night-shift
report instead of pausing for human ratification.

Phase A stub: shape only. Real persona invocations + MOM rendering land in
Phase B (Inception loop) and Phase C (Strike Panel during Construction).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ...instrumentation import instrumented_node


@instrumented_node("party.opened")
def _fan_out(state: dict) -> dict:
    return {"pitches": []}


@instrumented_node("party.pitch_received")
def _collect_pitch(state: dict) -> dict:
    return {}


@instrumented_node("party.consensus_reached")
def _consensus(state: dict) -> dict:
    auto = bool(state.get("night_shift_active"))
    return {"mom_ref": "stub://mom", "decision": "deferred", "auto": auto}


def build_party_graph(kind: str) -> Any:
    g = StateGraph(dict)
    g.add_node("fan_out", _fan_out)
    g.add_node("collect_pitch", _collect_pitch)
    g.add_node("consensus", _consensus)
    g.add_edge(START, "fan_out")
    g.add_edge("fan_out", "collect_pitch")
    g.add_edge("collect_pitch", "consensus")
    g.add_edge("consensus", END)
    return g.compile()
