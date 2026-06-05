"""Instrumentation: interrupts are control flow, never telemetry errors."""

from __future__ import annotations

import pdlc_graph.instrumentation as instr
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pdlc_graph.instrumentation import instrumented_node, set_emitter
from pdlc_graph.state import PDLCState


class _Capture:
    def __init__(self) -> None:
        self.types: list[str] = []

    def emit(self, event_type, state, payload, correlation_id):
        self.types.append(event_type)


@pytest.fixture
def cap():
    c = _Capture()
    set_emitter(c)
    yield c
    instr._emitter = instr._NullEmitter()  # restore the default null emitter


def test_interrupt_does_not_emit_error_event(cap):
    @instrumented_node("step.completed")
    def node(state: PDLCState) -> dict:
        interrupt({"kind": "approval", "gate": "x"})
        return {}

    g = StateGraph(PDLCState)
    g.add_node("node", node)
    g.add_edge(START, "node")
    g.add_edge("node", END)
    c = g.compile(checkpointer=MemorySaver())
    c.invoke({"org_id": "o", "project_id": "p"}, {"configurable": {"thread_id": "t"}})

    # The node paused at the interrupt — enter was emitted, but NOT an error.
    assert "step.completed" in cap.types
    assert "error" not in cap.types


def test_real_exception_still_emits_error(cap):
    @instrumented_node("step.completed")
    def boom(state: PDLCState) -> dict:
        raise ValueError("kaboom")

    g = StateGraph(PDLCState)
    g.add_node("boom", boom)
    g.add_edge(START, "boom")
    g.add_edge("boom", END)
    c = g.compile()
    with pytest.raises(ValueError):
        c.invoke({"org_id": "o", "project_id": "p"})
    assert "error" in cap.types
