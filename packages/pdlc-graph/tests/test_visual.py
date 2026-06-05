"""Tests for the visual companion spec + its wiring into the interrupt payload."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.graphs.brainstorm.discover import build_discover
from pdlc_graph.graphs.brainstorm.plan import build_plan
from pdlc_graph.ports import reset_artifact_store, reset_task_store
from pdlc_graph.visual import mermaid_screen, options_screen, visual


@pytest.fixture(autouse=True)
def _hermetic():
    reset_artifact_store()
    reset_task_store()
    yield


def _intr(g, cfg):
    snap = g.get_state(cfg)
    for task in snap.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    raise AssertionError("expected a pending interrupt but none was found")


def test_options_screen_auto_letters_and_keys():
    s = options_screen("Look & feel", [{"title": "A"}, {"title": "B"}], key="q0")
    assert s["type"] == "options" and s["key"] == "q0"
    assert [o["choice"] for o in s["options"]] == ["a", "b"]


def test_visual_wraps_screens():
    spec = visual([mermaid_screen("Tree", "graph TD\n a-->b")])
    assert spec["screens"][0]["type"] == "mermaid"
    assert "a-->b" in spec["screens"][0]["mermaid"]


def test_ux_discovery_interrupt_carries_options_visual():
    g = build_discover().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "vis"}}
    g.invoke(
        {"feature": "saved searches", "project_id": "p1", "interaction_mode": "socratic",
         "brainstorm_log": [], "visual": True},
        cfg,
    )
    # Drive the three Socratic rounds to reach UX Discovery.
    g.invoke(Command(resume={"answers": ["a", "b", "c", "d"]}), cfg)
    g.invoke(Command(resume={"answers": ["a", "b", "c"]}), cfg)
    g.invoke(Command(resume={"answers": ["a", "b"]}), cfg)
    ux = _intr(g, cfg)
    assert "UX Discovery" in (ux.get("context") or "")
    screens = ux["visual"]["screens"]
    assert [s["type"] for s in screens] == ["options", "options", "options"]
    assert [s["key"] for s in screens] == ["q0", "q1", "q2"]


def test_plan_gate_interrupt_carries_mermaid_visual():
    g = build_plan().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "plan"}}
    g.invoke(
        {"feature": "dark mode", "project_id": "p1",
         "prd_ref": "memory://p1/prd.md", "interaction_mode": "sketch"},
        cfg,
    )
    gate = _intr(g, cfg)
    assert gate["gate"] == "beads_tasklist_approve"
    screens = gate["visual"]["screens"]
    assert screens[0]["type"] == "mermaid"
    assert "graph TD" in screens[0]["mermaid"]
    assert "bd-1" in screens[0]["mermaid"]
