"""Top-level meta-graph — routes to one of six phase subgraphs.

The router consults `state.phase` and `state.night_shift_active`. Night-shift
overrides whatever phase is active because the autonomous loop wraps build +
ship in one supervised graph.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..state import PDLCState
from .brainstorm import brainstorm_graph
from .build import build_graph
from .init import init_graph
from .night_shift import night_shift_graph
from .ship import ship_graph
from .utility import utility_graph


def _route(state: PDLCState) -> str:
    if state.get("night_shift_active"):
        return "night_shift"
    # A utility command (/decide, /doctor, /pause, …) routes to the utility
    # subgraph regardless of the resting phase.
    if state.get("utility_command"):
        return "utility"
    return {
        "Initialization": "init",
        "Inception": "brainstorm",
        "Construction": "build",
        "Operation": "ship",
    }.get(state.get("phase", "Initialization"), "utility")


def build_meta_graph(checkpointer=None):
    """Compile the meta-graph. Pass a `checkpointer` (e.g. MemorySaver or
    PostgresSaver) to make `interrupt()` sites in the nested phase subgraphs
    resumable; without one the graph runs straight through (routing tests)."""
    g = StateGraph(PDLCState)
    g.add_node("init", init_graph)
    g.add_node("brainstorm", brainstorm_graph)
    g.add_node("build", build_graph)
    g.add_node("ship", ship_graph)
    g.add_node("night_shift", night_shift_graph)
    g.add_node("utility", utility_graph)
    g.add_conditional_edges(
        START,
        _route,
        {
            "init": "init",
            "brainstorm": "brainstorm",
            "build": "build",
            "ship": "ship",
            "night_shift": "night_shift",
            "utility": "utility",
        },
    )
    for node in ("init", "brainstorm", "build", "ship", "night_shift", "utility"):
        g.add_edge(node, END)
    return g.compile(checkpointer=checkpointer)
