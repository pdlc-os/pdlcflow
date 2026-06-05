"""Night-shift subgraph — autonomous Build + Ship with Sentinel on every edge.

Phase A stub: a single passthrough with a Sentinel-evaluator stub. The real
graph (preflight → contract_party → activate → loop[build/ship/sentinel] →
complete | abort) plus the three-layer prod-deploy ban lands in Phase F.
"""

from langgraph.graph import END, START, StateGraph

from ..instrumentation import instrumented_node
from ..sentinel.evaluator import evaluate
from ..state import PDLCState


@instrumented_node("night_shift.started")
def _activate(state: PDLCState) -> dict:
    return {"night_shift_active": True}


@instrumented_node("night_shift.verdict")
def _sentinel_eval(state: PDLCState) -> dict:
    verdict = evaluate(run_state={}, state_md="")
    return {"last_checkpoint": f"verdict={verdict['verdict']}"}


def _build():
    g = StateGraph(PDLCState)
    g.add_node("activate", _activate)
    g.add_node("sentinel_eval", _sentinel_eval)
    g.add_edge(START, "activate")
    g.add_edge("activate", "sentinel_eval")
    g.add_edge("sentinel_eval", END)
    return g.compile()


night_shift_graph = _build()
