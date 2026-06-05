"""Initialization subgraph — first-time setup, Constitution + Intent + Roadmap.

Phase A stub: a single passthrough node that emits phase.entered. The real
Initialization flow (skills/init/steps/*.md in upstream) lands in Phase B.
"""

from langgraph.graph import END, START, StateGraph

from ..instrumentation import instrumented_node
from ..state import PDLCState


@instrumented_node("phase.entered")
def _enter(state: PDLCState) -> dict:
    return {"sub_phase": "Initialization"}


def _build():
    g = StateGraph(PDLCState)
    g.add_node("enter", _enter)
    g.add_edge(START, "enter")
    g.add_edge("enter", END)
    return g.compile()


init_graph = _build()
