"""Utility subgraph — routes for /decide, /whatif, /doctor, /rollback,
/hotfix, /abandon, /release, /override, /pause, /resume.

Phase A stub: a single dispatch node. Real utility skills land in Phase E.
"""

from langgraph.graph import END, START, StateGraph

from ..instrumentation import instrumented_node
from ..state import PDLCState


@instrumented_node("skill.invoked")
def _dispatch(state: PDLCState) -> dict:
    return {}


def _build():
    g = StateGraph(PDLCState)
    g.add_node("dispatch", _dispatch)
    g.add_edge(START, "dispatch")
    g.add_edge("dispatch", END)
    return g.compile()


utility_graph = _build()
