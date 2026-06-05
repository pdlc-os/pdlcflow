"""Brainstorm subgraph — Discover → Define → Design → Plan.

Phase A stub: chains four placeholder nodes, one per sub-phase. The real
nodes (with party meetings, Socratic Q&A, threat modeling, Bloom's
Taxonomy, etc. from upstream skills/brainstorm/) land in Phase B.
"""

from langgraph.graph import END, START, StateGraph

from ..instrumentation import instrumented_node
from ..state import PDLCState


@instrumented_node("subphase.entered")
def _discover(state: PDLCState) -> dict:
    return {"sub_phase": "Discover"}


@instrumented_node("subphase.entered")
def _define(state: PDLCState) -> dict:
    return {"sub_phase": "Define"}


@instrumented_node("subphase.entered")
def _design(state: PDLCState) -> dict:
    return {"sub_phase": "Design"}


@instrumented_node("subphase.entered")
def _plan(state: PDLCState) -> dict:
    return {"sub_phase": "Plan"}


def _build():
    g = StateGraph(PDLCState)
    g.add_node("discover", _discover)
    g.add_node("define", _define)
    g.add_node("design", _design)
    g.add_node("plan", _plan)
    g.add_edge(START, "discover")
    g.add_edge("discover", "define")
    g.add_edge("define", "design")
    g.add_edge("design", "plan")
    g.add_edge("plan", END)
    return g.compile()


brainstorm_graph = _build()
