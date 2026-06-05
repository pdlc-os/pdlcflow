"""Build subgraph — Build → Review → Test.

Phase A stub: three passthrough nodes. The real Construction loop (TDD
enforcement, 3-Strike escalation, Strike Panel party meeting, 7-layer test
suite) lands in Phase C.
"""

from langgraph.graph import END, START, StateGraph

from ..instrumentation import instrumented_node
from ..state import PDLCState


@instrumented_node("subphase.entered")
def _build_loop(state: PDLCState) -> dict:
    return {"sub_phase": "Build"}


@instrumented_node("subphase.entered")
def _review(state: PDLCState) -> dict:
    return {"sub_phase": "Review"}


@instrumented_node("subphase.entered")
def _test(state: PDLCState) -> dict:
    return {"sub_phase": "Test"}


def _build():
    g = StateGraph(PDLCState)
    g.add_node("build_loop", _build_loop)
    g.add_node("review", _review)
    g.add_node("test", _test)
    g.add_edge(START, "build_loop")
    g.add_edge("build_loop", "review")
    g.add_edge("review", "test")
    g.add_edge("test", END)
    return g.compile()


build_graph = _build()
