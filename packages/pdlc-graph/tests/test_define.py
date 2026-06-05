"""Tests for the DEFINE sub-phase (gate kind 'prd_approve')."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.graphs.brainstorm.define import GATE_KIND, build_define, define_graph
from pdlc_graph.ports import get_artifact, reset_artifact_store, reset_task_store
from pdlc_graph.render import render_prd


@pytest.fixture(autouse=True)
def _reset_stores():
    reset_artifact_store()
    reset_task_store()
    yield
    reset_artifact_store()
    reset_task_store()


def _initial_state(**overrides) -> dict:
    state = {
        "feature": "GitHub OAuth Login",
        "project_id": "proj-1",
        "interaction_mode": "socratic",
        "brainstorm_log": [
            {"section": "Problem", "body": "Users must create a password account."},
            {"section": "Target User", "body": "Developers with GitHub accounts."},
        ],
    }
    state.update(overrides)
    return state


def test_gate_kind_is_prd_approve():
    assert GATE_KIND == "prd_approve"


def test_render_prd_is_pure_and_has_sections():
    md = render_prd(
        feature="Feature X",
        date="2026-06-05",
        overview="An overview.",
        problem_statement="A problem.",
        target_user="A user.",
        requirements={"must": ["do a thing"], "should": ["do another"], "may": []},
        assumptions=["assume this"],
        acceptance_criteria=["it works"],
        user_stories=[
            {
                "id": "US-001",
                "title": "Happy path",
                "acceptance": "1",
                "given": "context",
                "when": "action",
                "then": "outcome",
            }
        ],
        non_functional=["fast"],
        known_risks=["risky"],
        out_of_scope=["not this"],
    )
    for heading in (
        "# PRD: Feature X",
        "## Overview",
        "## Problem Statement",
        "## Target User",
        "## Requirements",
        "## Assumptions",
        "## Acceptance Criteria",
        "## User Stories",
        "## Non-Functional Requirements",
        "## Known Risks",
        "## Out of Scope",
        "## Design Docs",
        "## Approval",
    ):
        assert heading in md
    # RFC-2119 verbs interpolated, MUST before SHOULD.
    assert "The system MUST do a thing" in md
    assert "The system SHOULD do another" in md
    assert md.index("MUST do a thing") < md.index("SHOULD do another")
    # BDD story rendered.
    assert "**US-001: Happy path**" in md
    assert "Given context" in md
    # Deterministic.
    assert md == render_prd(
        feature="Feature X",
        date="2026-06-05",
        overview="An overview.",
        problem_statement="A problem.",
        target_user="A user.",
        requirements={"must": ["do a thing"], "should": ["do another"], "may": []},
        assumptions=["assume this"],
        acceptance_criteria=["it works"],
        user_stories=[
            {
                "id": "US-001",
                "title": "Happy path",
                "acceptance": "1",
                "given": "context",
                "when": "action",
                "then": "outcome",
            }
        ],
        non_functional=["fast"],
        known_risks=["risky"],
        out_of_scope=["not this"],
    )


def test_define_graph_is_precompiled():
    # Exposed compiled graph (no checkpointer) for composition.
    assert define_graph is not None


def test_socratic_pauses_at_gate_then_approves():
    g = build_define().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    out = g.invoke(_initial_state(), cfg)

    # PRD persisted before the gate.
    assert out.get("prd_ref")
    prd_md = get_artifact(out["prd_ref"])
    assert "# PRD: GitHub OAuth Login" in prd_md
    assert "**Status:** Draft" in prd_md

    # Paused at the approval gate interrupt (the gate node has not committed
    # a verdict yet).
    assert "prd_approved" not in out
    snapshot = g.get_state(cfg)
    assert snapshot.next == ("prd_gate",)
    interrupts = snapshot.tasks[0].interrupts
    assert interrupts and interrupts[0].value.get("gate") == "prd_approve"

    # Resume with approval.
    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["prd_approved"] is True


def test_socratic_rejection_records_false():
    g = build_define().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "reject"}}

    g.invoke(_initial_state(), cfg)
    final = g.invoke(Command(resume={"approved": False, "comment": "needs work"}), cfg)
    assert final["prd_approved"] is False


def test_night_shift_runs_to_completion_without_interrupt():
    g = build_define().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}

    out = g.invoke(_initial_state(night_shift_active=True), cfg)

    assert "__interrupt__" not in out
    assert out["prd_approved"] is True
    assert out.get("prd_ref")
    assert "# PRD: GitHub OAuth Login" in get_artifact(out["prd_ref"])
