"""Operation subgraph — Ship → Verify → Reflect (Phase D).

Composes the three Operation segments into one graph over PDLCState:

    ship (merge_and_deploy_approve) → verify (smoke_signoff) → reflect (episode_approve)

Each segment is a compiled StateGraph whose terminal node is its approval gate;
this parent chains them. Segments are added as compiled subgraphs (no inner
checkpointer) so their `interrupt()` sites propagate to the top-level graph's
checkpointer (MemorySaver in tests, PostgresSaver in the engine). `meta_graph`
imports `ship_graph` from here.
"""

from langgraph.graph import END, START, StateGraph

from ...state import PDLCState
from .reflect import reflect_graph
from .ship import ship_graph as ship_segment
from .verify import verify_graph

__all__ = ["build_operation", "ship_graph"]


def build_operation() -> StateGraph:
    """Uncompiled Operation graph: ship → verify → reflect."""
    g = StateGraph(PDLCState)
    g.add_node("ship", ship_segment)
    g.add_node("verify", verify_graph)
    g.add_node("reflect", reflect_graph)
    g.add_edge(START, "ship")
    g.add_edge("ship", "verify")
    g.add_edge("verify", "reflect")
    g.add_edge("reflect", END)
    return g


# `ship_graph` is the composed Operation graph (the name meta_graph imports).
ship_graph = build_operation().compile()
