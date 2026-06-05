"""Tests for the decisions-safety utility nodes.

Covers decide / doctor / whatif (pure, direct calls) and override (interrupt,
driven through a one-node MemorySaver graph, including a night-shift refusal).
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pdlc_graph.graphs.utility.decide import decide_node
from pdlc_graph.graphs.utility.doctor import doctor_node
from pdlc_graph.graphs.utility.override import override_node
from pdlc_graph.graphs.utility.whatif import whatif_node
from pdlc_graph.ports import get_artifact, reset_artifact_store, reset_task_store
from pdlc_graph.render import render_decisions, render_doctor
from pdlc_graph.state import PDLCState


@pytest.fixture(autouse=True)
def _reset_stores():
    reset_artifact_store()
    reset_task_store()
    yield
    reset_artifact_store()
    reset_task_store()


# ── renderers (pure) ───────────────────────────────────────────────────────


def test_render_decisions_empty():
    md = render_decisions([])
    assert "# Decisions" in md
    assert "_No decisions recorded._" in md


def test_render_decisions_table_and_escaping():
    md = render_decisions(
        [{"id": "D-1", "title": "Use Postgres", "rationale": "a | b", "date": "2026-06-05"}]
    )
    assert "| ID | Title | Rationale | Date |" in md
    assert "D-1" in md
    assert "Use Postgres" in md
    # pipe in a cell is escaped, not a column break
    assert "a \\| b" in md
    # deterministic
    assert md == render_decisions(
        [{"id": "D-1", "title": "Use Postgres", "rationale": "a | b", "date": "2026-06-05"}]
    )


def test_render_doctor_summary_and_status():
    report = {
        "feature": "Login",
        "phase": "Construction",
        "checks": {"has_feature": True, "no_blockers": False},
        "details": {"no_blockers": "2 active blocker(s)"},
    }
    md = render_doctor(report)
    assert "# Doctor Report" in md
    assert "1 passed, 1 failed" in md
    assert "| has_feature | PASS |" in md
    assert "| no_blockers | FAIL | 2 active blocker(s) |" in md


# ── decide ─────────────────────────────────────────────────────────────────


def test_decide_appends_with_provided_rationale():
    patch = decide_node(
        {
            "project_id": "proj-1",
            "utility_args": {"title": "Adopt LangGraph", "rationale": "It fits our model."},
            "decisions": [],
        }
    )
    decisions = patch["decisions"]
    assert len(decisions) == 1
    entry = decisions[0]
    assert entry["id"] == "D-1"
    assert entry["title"] == "Adopt LangGraph"
    assert entry["rationale"] == "It fits our model."
    assert entry["date"]
    assert patch["utility_result"] == {
        "command": "decide",
        "id": "D-1",
        "title": "Adopt LangGraph",
        "count": 1,
    }
    md = get_artifact(patch["decisions_ref"])
    assert "Adopt LangGraph" in md


def test_decide_drafts_rationale_when_missing():
    patch = decide_node(
        {"project_id": "p", "utility_args": {"title": "Pick a queue"}, "decisions": []}
    )
    rationale = patch["decisions"][0]["rationale"]
    assert rationale  # drafted by the offline stub
    assert rationale.startswith("[stub:atlas")


def test_decide_increments_over_existing():
    existing = [{"id": "D-1", "title": "Old", "rationale": "r", "date": "2026-01-01"}]
    patch = decide_node(
        {"project_id": "p", "utility_args": {"title": "New", "rationale": "r2"}, "decisions": existing}
    )
    assert [d["id"] for d in patch["decisions"]] == ["D-1", "D-2"]
    assert len(patch["decisions"]) == 2


# ── doctor ─────────────────────────────────────────────────────────────────


def test_doctor_healthy_report():
    patch = doctor_node(
        {
            "project_id": "p",
            "feature": "Login",
            "phase": "Construction",
            "roadmap_claim": {"feature_id": "F-1"},
            "active_blockers": [],
        }
    )
    report = patch["doctor_report"]
    assert report["checks"]["has_feature"] is True
    assert report["checks"]["no_blockers"] is True
    assert report["failed"] == 0
    assert patch["utility_result"]["healthy"] is True
    assert "PASS" in get_artifact(patch["doctor_ref"])


def test_doctor_flags_problems():
    patch = doctor_node(
        {
            "project_id": "p",
            "feature": None,
            "phase": "Inception",
            "paused": True,
            "abandoned": False,
            "roadmap_claim": None,
            "active_blockers": [{"id": "b1"}, {"id": "b2"}],
        }
    )
    report = patch["doctor_report"]
    assert report["checks"]["has_feature"] is False
    assert report["checks"]["not_paused"] is False
    assert report["checks"]["has_roadmap_claim"] is False
    assert report["checks"]["no_blockers"] is False
    assert report["blocker_count"] == 2
    assert report["failed"] >= 4
    assert patch["utility_result"]["healthy"] is False


# ── whatif (read-only) ──────────────────────────────────────────────────────


def test_whatif_produces_artifact_and_summary():
    patch = whatif_node(
        {"project_id": "p", "utility_args": {"scenario": "What if we drop the cache?"}}
    )
    assert patch["utility_result"] == {
        "command": "whatif",
        "scenario": "What if we drop the cache?",
        "read_only": True,
    }
    md = get_artifact(patch["whatif_ref"])
    assert "# What-If Analysis" in md
    assert "What if we drop the cache?" in md
    assert "read-only" in md.lower()


def test_whatif_does_not_mutate_state():
    patch = whatif_node(
        {
            "project_id": "p",
            "utility_args": {"scenario": "What if we rewrite in Rust?"},
            "paused": False,
            "abandoned": False,
            "decisions": [],
            "roadmap_claim": {"feature_id": "F-9"},
        }
    )
    forbidden = {"paused", "abandoned", "decisions", "roadmap_claim", "phase", "feature"}
    assert forbidden.isdisjoint(patch.keys())
    assert set(patch.keys()) == {"whatif_ref", "utility_result"}


# ── override (interrupt) ────────────────────────────────────────────────────


def _override_graph() -> StateGraph:
    g = StateGraph(PDLCState)
    g.add_node("n", override_node)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    return g


def test_override_confirmed_with_red_red():
    g = _override_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ok"}}

    out = g.invoke({"utility_args": {"reason": "hotfix prod"}}, cfg)
    # Paused at the confirmation interrupt.
    assert "override_log" not in out
    snapshot = g.get_state(cfg)
    interrupts = snapshot.tasks[0].interrupts
    assert interrupts
    val = interrupts[0].value
    assert val["mode"] == "override_confirm"
    assert val["reason"] == "hotfix prod"

    final = g.invoke(Command(resume="red red"), cfg)
    log = final["override_log"]
    assert log[-1]["confirmed"] is True
    assert log[-1]["reason"] == "hotfix prod"
    assert final["utility_result"] == {
        "command": "override",
        "confirmed": True,
        "outcome": "confirmed",
    }


def test_override_cancelled_on_wrong_phrase():
    g = _override_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "no"}}

    g.invoke({"utility_args": {"reason": "nope"}}, cfg)
    final = g.invoke(Command(resume="yes do it"), cfg)
    assert final["override_log"][-1]["confirmed"] is False
    assert final["utility_result"]["confirmed"] is False
    assert final["utility_result"]["outcome"] == "cancelled"


def test_override_accepts_dict_resume():
    g = _override_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "dict"}}

    g.invoke({"utility_args": {"reason": "r"}}, cfg)
    final = g.invoke(Command(resume={"answer": "RED RED"}), cfg)
    assert final["override_log"][-1]["confirmed"] is True


def test_override_night_shift_refuses_without_interrupt():
    g = _override_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}

    out = g.invoke(
        {"utility_args": {"reason": "auto"}, "night_shift_active": True}, cfg
    )
    assert "__interrupt__" not in out
    assert out["override_log"][-1] == {
        "reason": "auto",
        "confirmed": False,
        "date": out["override_log"][-1]["date"],
    }
    assert out["utility_result"] == {"command": "override", "refused": "night-shift"}
