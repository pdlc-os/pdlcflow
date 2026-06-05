"""Tests for the Reflect sub-phase (Operation, gate episode_approve)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.deploy_port import reset_deploy_register
from pdlc_graph.graphs.ship.reflect import GATE_KIND, build_reflect, reflect_graph
from pdlc_graph.ports import get_artifact, reset_artifact_store, reset_task_store
from pdlc_graph.render import render_episode, render_metrics
from pdlc_graph.test_runner_port import reset_test_runner
from pdlc_graph.vcs_port import reset_vcs


@pytest.fixture(autouse=True)
def _hermetic():
    reset_artifact_store()
    reset_task_store()
    reset_deploy_register()
    reset_vcs()
    reset_test_runner()
    yield


def _initial(**over) -> dict:
    base = {
        "feature": "dark mode",
        "project_id": "p1",
        "version": "v1.3.0",
        "review_ref": "artifact://p1/docs/pdlc/reviews/REVIEW.md",
        "build_log": [
            {"task_id": "bd-1", "status": "done"},
            {"task_id": "bd-2", "status": "done"},
        ],
        "construction_test_results": {
            "unit": {"passed": True, "report": "ok"},
            "e2e": {"passed": True, "report": "ok"},
        },
        "strike_history": [],
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
# Pure renderers
# --------------------------------------------------------------------------- #
def test_render_episode_is_pure_with_all_sections():
    md = render_episode(
        feature="dark mode",
        episode_id="001",
        date="2026-06-05",
        what_was_built="Added a dark theme toggle.",
        links={"PR": "#42"},
        decisions=["Used CSS variables."],
        test_summary="2/2 layers passed.",
        tradeoffs=["No system-pref auto-detect yet."],
        agent_team=["Jarvis (Tech Writer)"],
        reflect_notes={"went_well": ["clean build"], "broke": ["flaky e2e"], "improve": ["pin deps"]},
    )
    assert "# Episode 001: dark mode" in md
    assert "pdlc-template-version" in md
    for section in (
        "## What Was Built",
        "## Links",
        "## Key Decisions & Rationale",
        "## Test Summary",
        "## Known Tradeoffs & Tech Debt Introduced",
        "## Agent Team",
        "## Reflect Notes",
    ):
        assert section in md
    assert "clean build" in md and "flaky e2e" in md and "pin deps" in md
    assert "1. Used CSS variables." in md


def test_render_metrics_is_pure_with_row_and_trend():
    md = render_metrics(
        feature="dark mode",
        episode_id="001",
        date="2026-06-05",
        cycle_days=3,
        test_pass_pct=100.0,
        review_rounds=1,
        strikes=0,
        tasks=2,
    )
    assert "## Delivery Metrics" in md
    assert "## Trend" in md
    assert "| 001 | dark mode | Feature | 3 | 100% | 1 | 0 | 2 | 2026-06-05 |" in md
    assert "Episode 001 shipped in 3 day(s)" in md


# --------------------------------------------------------------------------- #
# Happy path — pauses at the episode_approve gate
# --------------------------------------------------------------------------- #
def test_reflect_pauses_at_episode_gate_then_completes():
    g = build_reflect().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "happy"}}

    g.invoke(_initial(), cfg)
    gate = _intr(g, cfg)
    assert gate["kind"] == "approval"
    assert gate["gate"] == GATE_KIND == "episode_approve"
    assert gate["episode_ref"]

    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["episode_approved"] is True
    assert final["operation_complete"] is True
    assert final["episode_ref"]
    assert final["metrics_ref"]
    assert final["roadmap_claim"] is None
    assert final["sub_phase"] == "Reflect"
    assert final["handoff"]["phase_completed"] == "Operation"
    assert final["handoff"]["next_phase"] == "Idle"
    assert final["handoff"]["next_action"] == "Run /brainstorm for the next feature"

    # Episode + metrics artifacts are real rendered markdown.
    assert "# Episode 001: dark mode" in get_artifact(final["episode_ref"])
    assert "## Delivery Metrics" in get_artifact(final["metrics_ref"])


def test_reflect_rejection_records_false():
    g = build_reflect().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "reject"}}

    g.invoke(_initial(), cfg)
    _intr(g, cfg)
    final = g.invoke(Command(resume={"approved": False}), cfg)
    assert final["episode_approved"] is False
    # Wrap-up still runs and completes the loop.
    assert final["operation_complete"] is True


# --------------------------------------------------------------------------- #
# Night-shift — no human turns
# --------------------------------------------------------------------------- #
def test_night_shift_runs_to_completion_without_interrupt():
    g = build_reflect().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}

    out = g.invoke(_initial(night_shift_active=True), cfg)
    assert g.get_state(cfg).next == ()  # ran to completion
    assert out["episode_approved"] is True  # auto-approved
    assert out["operation_complete"] is True
    assert out["metrics_ref"]
    assert out["roadmap_claim"] is None


def test_compiled_graph_is_importable():
    # The composition-ready compiled graph exists (no inner checkpointer).
    assert reflect_graph is not None
