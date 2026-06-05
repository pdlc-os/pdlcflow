"""Tests for the PLAN sub-phase (gate kind beads_tasklist_approve)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.graphs.brainstorm.plan import build_plan
from pdlc_graph.ports import get_task_store, reset_artifact_store, reset_task_store
from pdlc_graph.ports.artifacts import get_artifact
from pdlc_graph.render import render_plan


@pytest.fixture(autouse=True)
def _reset():
    reset_artifact_store()
    reset_task_store()
    yield
    reset_artifact_store()
    reset_task_store()


def _initial(**over) -> dict:
    base = {
        "feature": "dark mode",
        "project_id": "proj-1",
        "prd_ref": "memory://proj-1/docs/pdlc/prds/PRD_dark-mode_2026-06-05.md",
        "interaction_mode": "socratic",
    }
    base.update(over)
    return base


def test_plan_pauses_at_gate_then_approves():
    g = build_plan().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    g.invoke(_initial(), cfg)

    # langgraph 0.2.x does not surface "__interrupt__" in invoke() output; the
    # pending interrupt is read from the state snapshot instead.
    snapshot = g.get_state(cfg)
    assert snapshot.next == ("plan_gate",)  # paused at the approval gate
    intr = snapshot.tasks[0].interrupts[0].value
    assert intr["gate"] == "beads_tasklist_approve"
    assert intr["task_count"] == 4
    assert intr["wave_count"] >= 1

    # Tasks were created in the store with bd-NN external ids.
    tasks = get_task_store().list("proj-1")
    assert len(tasks) == 4
    assert all(t["external_id"].startswith("bd-") for t in tasks)

    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["plan_approved"] is True
    assert final["plan_ref"].endswith(".md")
    assert final["handoff"]["next_phase"] == "Construction / Build"


def test_plan_dependencies_and_plan_file():
    g = build_plan().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t2"}}
    g.invoke(_initial(), cfg)
    final = g.invoke(Command(resume={"approved": True}), cfg)

    store_tasks = {t["external_id"]: t for t in get_task_store().list("proj-1")}
    # Skeleton: bd-2 depends on bd-1; bd-4 depends on bd-2 and bd-3.
    assert store_tasks["bd-2"]["depends_on"] == ["bd-1"]
    assert set(store_tasks["bd-4"]["depends_on"]) == {"bd-2", "bd-3"}

    plan_md = get_artifact(final["plan_ref"])
    assert "## Tasks" in plan_md
    assert "```mermaid" in plan_md
    assert "## Implementation Order" in plan_md
    assert "bd-1" in plan_md and "bd-4" in plan_md


def test_plan_rejection_records_false():
    g = build_plan().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t3"}}
    g.invoke(_initial(), cfg)
    final = g.invoke(Command(resume={"approved": False}), cfg)
    assert final["plan_approved"] is False


def test_night_shift_runs_to_completion_without_interrupt():
    g = build_plan().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}
    out = g.invoke(_initial(night_shift_active=True), cfg)
    assert "__interrupt__" not in out
    assert out["plan_approved"] is True
    assert out["plan_ref"].endswith(".md")
    assert len(get_task_store().list("proj-1")) == 4


def test_render_plan_is_pure():
    tasks = [
        {"external_id": "bd-1", "title": "A", "labels": ["domain:backend"], "depends_on": []},
        {"external_id": "bd-2", "title": "B", "labels": ["domain:frontend"], "depends_on": ["bd-1"]},
    ]
    md = render_plan(
        feature="x",
        date="2026-06-05",
        prd_ref="memory://p/prd.md",
        tasks=tasks,
        mermaid="graph TD\n    bd-1 --> bd-2",
        waves=[["bd-1"], ["bd-2"]],
    )
    assert "| bd-1 | A |" in md
    assert "bd-1 --> bd-2" in md
    assert "Wave 1" in md and "Wave 2" in md
