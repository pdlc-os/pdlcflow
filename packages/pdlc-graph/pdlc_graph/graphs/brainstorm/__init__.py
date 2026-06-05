"""Brainstorm subgraph — Discover → Define → Design → Plan (Inception, Phase B).

Composes the four sub-phase subgraphs into one Inception graph. Each
sub-phase is a compiled StateGraph(PDLCState) whose terminal node is its
approval gate; this parent chains them in order. The sub-phases are added as
compiled subgraphs (no inner checkpointer) so `interrupt()` sites in any of
them propagate to whatever checkpointer the top-level graph is compiled with
(MemorySaver in tests, PostgresSaver in the engine).
"""

from langgraph.graph import END, START, StateGraph

from ...state import PDLCState
from .define import define_graph
from .design import design_graph
from .discover import discover_graph
from .plan import plan_graph

__all__ = ["brainstorm_graph", "build_brainstorm"]


def build_brainstorm() -> StateGraph:
    """Uncompiled Inception graph: discover → define → design → plan."""
    g = StateGraph(PDLCState)
    g.add_node("discover", discover_graph)
    g.add_node("define", define_graph)
    g.add_node("design", design_graph)
    g.add_node("plan", plan_graph)
    g.add_edge(START, "discover")
    g.add_edge("discover", "define")
    g.add_edge("define", "design")
    g.add_edge("design", "plan")
    g.add_edge("plan", END)
    return g


brainstorm_graph = build_brainstorm().compile()
