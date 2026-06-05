"""Construction subgraph — Build → Review → Test (Phase C).

Composes the Construction sub-phases into one graph over PDLCState:

    preflight → build_loop → review_party → review_gate → test_phase → wrap_up

`build_loop` runs the per-task TDD micro-loop with 3-Strike → Strike Panel
(interrupts inside one replay-safe node); `review_gate` is the single
Construction approval gate (#5, review_md_approve). Compiled without an inner
checkpointer so interrupts propagate to the top-level graph's checkpointer.
"""

from langgraph.graph import END, START, StateGraph

from ...state import PDLCState
from .loop import build_loop
from .preflight import preflight
from .review import review_gate, review_party
from .test_phase import test_phase, wrap_up

__all__ = ["build_construction", "build_graph"]


def build_construction() -> StateGraph:
    """Uncompiled Construction graph (START..steps..gate..END)."""
    g = StateGraph(PDLCState)
    g.add_node("preflight", preflight)
    g.add_node("build_loop", build_loop)
    g.add_node("review_party", review_party)
    g.add_node("review_gate", review_gate)
    g.add_node("test_phase", test_phase)
    g.add_node("wrap_up", wrap_up)
    g.add_edge(START, "preflight")
    g.add_edge("preflight", "build_loop")
    g.add_edge("build_loop", "review_party")
    g.add_edge("review_party", "review_gate")
    g.add_edge("review_gate", "test_phase")
    g.add_edge("test_phase", "wrap_up")
    g.add_edge("wrap_up", END)
    return g


build_graph = build_construction().compile()
