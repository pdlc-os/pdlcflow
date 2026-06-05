"""Ship subgraph — Ship → Verify → Reflect.

Phase A stub. Real Operation loop lands in Phase D (deploy register integration,
smoke runners, UX verify, episode generation, metrics rollup).
"""

from langgraph.graph import END, START, StateGraph

from ..instrumentation import instrumented_node
from ..state import PDLCState


@instrumented_node("subphase.entered")
def _ship(state: PDLCState) -> dict:
    return {"sub_phase": "Ship"}


@instrumented_node("subphase.entered")
def _verify(state: PDLCState) -> dict:
    return {"sub_phase": "Verify"}


@instrumented_node("subphase.entered")
def _reflect(state: PDLCState) -> dict:
    return {"sub_phase": "Reflect"}


def _build():
    g = StateGraph(PDLCState)
    g.add_node("ship", _ship)
    g.add_node("verify", _verify)
    g.add_node("reflect", _reflect)
    g.add_edge(START, "ship")
    g.add_edge("ship", "verify")
    g.add_edge("verify", "reflect")
    g.add_edge("reflect", END)
    return g.compile()


ship_graph = _build()
