"""Utility subgraph — dispatches by `utility_command` to one command node.

Commands (Phase E): /pause /resume /abandon /release /decide /doctor /whatif
/override /rollback /hotfix. Each lives in its own module exposing a
`<cmd>_node(state) -> patch`; this dispatcher routes `state["utility_command"]`
to the matching node. `interrupt()` sites (override double-RED, hotfix confirm)
propagate to the top-level checkpointer. `meta_graph` imports `utility_graph`.
"""

from langgraph.graph import END, START, StateGraph

from ...instrumentation import instrumented_node
from ...state import PDLCState
from .abandon import abandon_node
from .decide import decide_node
from .doctor import doctor_node
from .hotfix import hotfix_node
from .override import override_node
from .pause import pause_node
from .release import release_node
from .resume import resume_node
from .rollback import rollback_node
from .whatif import whatif_node

__all__ = ["UTILITY_NODES", "build_utility", "utility_graph"]

UTILITY_NODES = {
    "pause": pause_node,
    "resume": resume_node,
    "abandon": abandon_node,
    "release": release_node,
    "decide": decide_node,
    "doctor": doctor_node,
    "whatif": whatif_node,
    "override": override_node,
    "rollback": rollback_node,
    "hotfix": hotfix_node,
}


@instrumented_node("skill.invoked")
def _unknown(state: PDLCState) -> dict:
    return {
        "utility_result": {
            "command": state.get("utility_command"),
            "error": "unknown utility command",
        }
    }


def _route(state: PDLCState) -> str:
    cmd = state.get("utility_command")
    return cmd if cmd in UTILITY_NODES else "_unknown"


def build_utility() -> StateGraph:
    """Uncompiled utility dispatcher over PDLCState."""
    g = StateGraph(PDLCState)
    for name, fn in UTILITY_NODES.items():
        g.add_node(name, fn)
    g.add_node("_unknown", _unknown)
    g.add_conditional_edges(
        START, _route, {**{k: k for k in UTILITY_NODES}, "_unknown": "_unknown"}
    )
    for name in UTILITY_NODES:
        g.add_edge(name, END)
    g.add_edge("_unknown", END)
    return g


utility_graph = build_utility().compile()
