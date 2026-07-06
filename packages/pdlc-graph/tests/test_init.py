"""Tests for the Initialization sub-phase (T3-2, gate #1 `init_approve`).

Drives the ask rounds + the init_approve gate over a MemorySaver, mirroring the
brainstorm-flow test style, and asserts the three genesis artifacts are
rendered/persisted and the phase advances to Inception on approval.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.gates import GATE_KINDS
from pdlc_graph.graphs.init import GATE_KIND, build_init
from pdlc_graph.ports import get_artifact, reset_artifact_store, reset_task_store


@pytest.fixture(autouse=True)
def _hermetic():
    reset_artifact_store()
    reset_task_store()
    yield
    reset_artifact_store()
    reset_task_store()


def _initial(**overrides) -> dict:
    base = {
        "feature": "acme app",
        "project_name": "Acme",
        "project_id": "proj-1",
        "interaction_mode": "socratic",
        "phase": "Initialization",
    }
    base.update(overrides)
    return base


def _intr(g, cfg):
    for task in g.get_state(cfg).tasks:
        if task.interrupts:
            return task.interrupts[0].value
    raise AssertionError("expected a pending interrupt but none was found")


def test_init_approve_is_the_first_canonical_gate():
    assert GATE_KINDS[0] == "init_approve"
    assert len(GATE_KINDS) == 9


def test_init_flow_asks_three_rounds_then_gates_and_advances():
    g = build_init().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t-init"}}

    g.invoke(_initial(), cfg)
    # Round 1 — product intent
    r1 = _intr(g, cfg)
    assert r1["kind"] == "user_input_required" and "Product intent" in r1["context"]
    g.invoke(Command(resume={"answers": [
        "Ship features faster", "Small product teams", "Cycle time down 30%"]}), cfg)
    # Round 2 — constitution
    r2 = _intr(g, cfg)
    assert "Constitution" in r2["context"]
    g.invoke(Command(resume={"answers": ["No hard deletes", "sketch"]}), cfg)
    # Round 3 — seed roadmap
    r3 = _intr(g, cfg)
    assert "Seed roadmap" in r3["context"]
    g.invoke(Command(resume={"answers": ["Auth\nBilling", "gate access\ncharge money"]}), cfg)

    # Now the init_approve gate is pending with the three refs.
    gate = _intr(g, cfg)
    assert gate["kind"] == "approval" and gate["gate"] == GATE_KIND
    assert gate["constitution_ref"] and gate["intent_ref"] and gate["roadmap_ref"]

    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["init_approved"] is True
    assert final["phase"] == "Inception"  # advances to Inception on approval

    # The three genesis artifacts were rendered + persisted with the answers.
    consti = get_artifact(final["constitution_ref"])
    assert "# Constitution — Acme" in consti and "sketch" in consti and "No hard deletes" in consti
    intent = get_artifact(final["intent_ref"])
    assert "Ship features faster" in intent and "Small product teams" in intent
    roadmap = get_artifact(final["roadmap_ref"])
    assert "F-001" in roadmap and "Auth" in roadmap and "Billing" in roadmap and "gate access" in roadmap


def test_init_rejection_keeps_phase_in_initialization():
    g = build_init().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t-reject"}}
    g.invoke(_initial(), cfg)
    for answers in ([""], [""], [""]):  # blow through the three ask rounds tersely
        _intr(g, cfg)
        g.invoke(Command(resume={"answers": answers}), cfg)
    _intr(g, cfg)  # the gate
    final = g.invoke(Command(resume={"approved": False}), cfg)
    assert final["init_approved"] is False
    assert final.get("phase", "Initialization") == "Initialization"  # no advance


def test_init_auto_approves_under_night_shift():
    g = build_init().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t-ns"}}
    # night_shift_active auto-accepts ask drafts AND the gate — runs to the end
    # with no human turn.
    final = g.invoke(_initial(night_shift_active=True), cfg)
    assert final["init_approved"] is True and final["phase"] == "Inception"
    assert final["constitution_ref"]
