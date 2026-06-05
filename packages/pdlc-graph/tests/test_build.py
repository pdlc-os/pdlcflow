"""Tests for the Construction sub-phase (Build → Review → Test, gate review_md_approve)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.graphs.build import build_construction
from pdlc_graph.ports import get_artifact, reset_artifact_store, reset_task_store
from pdlc_graph.render import render_review
from pdlc_graph.test_runner_port import TDDViolation, assert_red_before_green, reset_test_runner


@pytest.fixture(autouse=True)
def _hermetic():
    reset_artifact_store()
    reset_task_store()
    reset_test_runner()
    yield


def _tasks(strike_on: str | None = None) -> list[dict]:
    tasks = [
        {"external_id": "bd-1", "title": "data model", "labels": ["domain:backend"], "depends_on": [], "wave": 1},
        {"external_id": "bd-2", "title": "api", "labels": ["domain:backend"], "depends_on": ["bd-1"], "wave": 2},
        {"external_id": "bd-3", "title": "ui", "labels": ["domain:frontend"], "depends_on": ["bd-2"], "wave": 3},
        {"external_id": "bd-4", "title": "tests", "labels": ["domain:devops"], "depends_on": ["bd-2", "bd-3"], "wave": 4},
    ]
    if strike_on:
        for t in tasks:
            if t["external_id"] == strike_on:
                t["simulate_failures"] = 3
    return tasks


def _initial(**over) -> dict:
    base = {
        "feature": "dark mode",
        "project_id": "p1",
        "interaction_mode": "sketch",
        "tasks": _tasks(),
    }
    base.update(over)
    return base


def _intr(g, cfg):
    snap = g.get_state(cfg)
    for task in snap.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    raise AssertionError("expected a pending interrupt but none was found")


# --------------------------------------------------------------------------- #
# TDD enforcement
# --------------------------------------------------------------------------- #
def test_tdd_guard_rejects_implementation_before_failing_test():
    with pytest.raises(TDDViolation):
        assert_red_before_green(has_failing_test=False, task_id="bd-1")
    # With a failing test recorded, the green phase is allowed (no raise).
    assert_red_before_green(has_failing_test=True, task_id="bd-1")


def test_render_review_is_pure_and_orders_by_severity():
    md = render_review(
        feature="x",
        date="2026-06-05",
        reviewers=["neo", "echo"],
        findings=[
            {"severity": "Advisory", "reviewer": "echo", "title": "minor", "reference": "x", "action": "consider"},
            {"severity": "Critical", "reviewer": "neo", "title": "bug", "reference": "y", "action": "fix"},
        ],
    )
    assert "# Review — x" in md
    assert "pdlc-template-version" in md
    # Critical sorted above Advisory.
    assert md.index("bug") < md.index("minor")
    assert "1 Critical" in md


# --------------------------------------------------------------------------- #
# Happy path — no strikes
# --------------------------------------------------------------------------- #
def test_happy_path_builds_then_pauses_at_review_gate():
    g = build_construction().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "happy"}}

    g.invoke(_initial(), cfg)
    # No simulated failures -> build_loop runs straight through; first pause is
    # the End-of-Review approval gate.
    gate = _intr(g, cfg)
    assert gate["kind"] == "approval"
    assert gate["gate"] == "review_md_approve"

    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["review_approved"] is True
    assert final["construction_complete"] is True
    assert final["review_ref"]
    # Every task built; all 7 layers recorded.
    assert len(final["build_log"]) == 4
    assert all(b["status"] == "done" for b in final["build_log"])
    assert set(final["construction_test_results"]) == {
        "unit", "integration", "contract", "e2e", "security", "perf", "ux"
    }
    assert final["handoff"]["next_phase"] == "Operation / Ship"

    # REVIEW.md is real rendered markdown.
    assert "# Review — dark mode" in get_artifact(final["review_ref"])


# --------------------------------------------------------------------------- #
# 3-Strike → Strike Panel
# --------------------------------------------------------------------------- #
def test_third_strike_convenes_panel_then_resumes():
    g = build_construction().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "strike"}}

    g.invoke(_initial(tasks=_tasks(strike_on="bd-2")), cfg)
    panel = _intr(g, cfg)
    assert panel["mode"] == "strike_panel"
    assert panel["task_id"] == "bd-2"
    assert len(panel["options"]) == 3

    # Human picks approach 0; the build loop resumes and finishes.
    g.invoke(Command(resume={"answers": ["0"]}), cfg)
    gate = _intr(g, cfg)
    assert gate["gate"] == "review_md_approve"

    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["construction_complete"] is True
    assert len(final["strike_history"]) == 1
    assert final["strike_history"][0]["task_id"] == "bd-2"
    assert final["strike_history"][0]["choice"] == 0
    # The struck task still completed.
    struck = next(b for b in final["build_log"] if b["task_id"] == "bd-2")
    assert struck["struck"] is True and struck["passed"] is True


# --------------------------------------------------------------------------- #
# Test sub-phase — required-layer failure pauses for a human decision
# --------------------------------------------------------------------------- #
def test_required_layer_failure_pauses_in_test_phase():
    g = build_construction().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "testfail"}}

    g.invoke(_initial(simulate_failing_layers=["unit"]), cfg)
    assert _intr(g, cfg)["gate"] == "review_md_approve"
    g.invoke(Command(resume={"approved": True}), cfg)
    # A required layer failed -> the Test sub-phase pauses for accept/fix/defer.
    decision = _intr(g, cfg)
    assert decision["mode"] == "test_failures"
    assert "unit" in decision["failed_layers"]

    final = g.invoke(Command(resume={"answers": ["accept"]}), cfg)
    assert final["construction_complete"] is True
    assert final["construction_test_results"]["unit"]["passed"] is False


# --------------------------------------------------------------------------- #
# Night-shift — no human turns
# --------------------------------------------------------------------------- #
def test_night_shift_runs_to_completion_without_interrupt():
    g = build_construction().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}

    out = g.invoke(_initial(tasks=_tasks(strike_on="bd-2"), night_shift_active=True), cfg)
    assert g.get_state(cfg).next == ()  # ran to completion
    assert out["construction_complete"] is True
    assert out["review_approved"] is True  # no Critical findings -> auto-approved
    assert len(out["build_log"]) == 4
    # The strike was auto-resolved (recommended approach).
    assert out["strike_history"][0]["auto"] is True
    assert out["strike_history"][0]["choice"] == 0
