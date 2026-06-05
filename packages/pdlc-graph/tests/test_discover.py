"""Tests for the DISCOVER sub-phase (steps 0-6, gate `discover_summary`)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.graphs.brainstorm.discover import GATE_KIND, build_discover, discover_graph
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
        "feature": "saved searches",
        "project_id": "proj-1",
        "interaction_mode": "socratic",
        "brainstorm_log": [],
    }
    base.update(overrides)
    return base


def _intr(g, cfg):
    """Pending interrupt value (langgraph 0.2.x has no __interrupt__ key).

    Reads from `tasks[].interrupts` rather than `.next`: when a single node
    interrupts repeatedly in a loop (Socratic rounds), `.next` is empty between
    resumes but the pending interrupt is still attached to the task.
    """
    snap = g.get_state(cfg)
    for task in snap.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    raise AssertionError("expected a pending interrupt but none was found")


def test_gate_kind_and_precompiled():
    assert GATE_KIND == "discover_summary"
    assert discover_graph is not None


def test_socratic_runs_three_rounds_then_gate():
    g = build_discover().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    g.invoke(_initial(), cfg)
    assert "Problem Statement" in (_intr(g, cfg).get("context") or "")

    g.invoke(Command(resume={"answers": ["a", "b", "c", "d"]}), cfg)
    assert "Future State" in (_intr(g, cfg).get("context") or "")

    g.invoke(Command(resume={"answers": ["a", "b", "c"]}), cfg)
    assert "Acceptance Criteria" in (_intr(g, cfg).get("context") or "")

    g.invoke(Command(resume={"answers": ["a", "b"]}), cfg)
    gate = _intr(g, cfg)
    assert gate["kind"] == "approval"
    assert gate["gate"] == "discover_summary"

    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["party_results"]["discover_summary"]["approved"] is True
    assert final["discovery_summary"]

    sections = [e["section"] for e in final["brainstorm_log"]]
    for expected in (
        "Socratic Discovery",
        "Progressive Thinking (Agent Team Meeting)",
        "Adversarial Review",
        "Edge Case Analysis",
        "Discovery Summary",
    ):
        assert expected in sections
    # No visual signal -> UX Discovery skipped.
    assert "UX Discovery" not in sections


def test_visual_signal_inserts_ux_discovery():
    g = build_discover().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "vis"}}

    g.invoke(_initial(visual=True), cfg)
    # Drive the three Socratic rounds.
    g.invoke(Command(resume={"answers": ["a", "b", "c", "d"]}), cfg)
    g.invoke(Command(resume={"answers": ["a", "b", "c"]}), cfg)
    g.invoke(Command(resume={"answers": ["a", "b"]}), cfg)
    # With a visual signal the next pause is the Muse-led UX Discovery round.
    ux = _intr(g, cfg)
    assert "UX Discovery" in (ux.get("context") or "")

    g.invoke(Command(resume={"answers": ["layout", "flow", "states"]}), cfg)
    assert _intr(g, cfg)["gate"] == "discover_summary"

    final = g.invoke(Command(resume={"approved": True}), cfg)
    sections = [e["section"] for e in final["brainstorm_log"]]
    assert "UX Discovery" in sections


def test_night_shift_runs_to_completion_without_interrupt():
    g = build_discover().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}

    out = g.invoke(_initial(night_shift_active=True), cfg)
    assert g.get_state(cfg).next == ()  # ran to completion, no pause
    assert out["party_results"]["discover_summary"]["approved"] is True
    assert out["discovery_summary"]
    # Discovery summary persisted as a real artifact.
    summary_entry = next(e for e in out["brainstorm_log"] if e["section"] == "Discovery Summary")
    uri = summary_entry["body"].split("Persisted at ", 1)[1].strip()
    assert "# Discovery Summary" in get_artifact(uri)
