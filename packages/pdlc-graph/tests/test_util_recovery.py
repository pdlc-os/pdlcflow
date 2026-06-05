"""Tests for the recovery utility nodes — /rollback (pure) and /hotfix (interrupt).

Hermetic: artifact and deploy-register stores are reset per test. The pure
rollback node is called directly; the interrupting hotfix node is driven
through a one-node MemorySaver graph (confirm / reject / night-shift paths).
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from pdlc_graph.deploy_port import (
    DeployBanError,
    get_deploy_register,
    reset_deploy_register,
)
from pdlc_graph.graphs.utility.hotfix import hotfix_node
from pdlc_graph.graphs.utility.rollback import rollback_node
from pdlc_graph.ports import get_artifact, reset_artifact_store, reset_task_store
from pdlc_graph.state import PDLCState


@pytest.fixture(autouse=True)
def _reset_stores():
    reset_artifact_store()
    reset_task_store()
    reset_deploy_register()
    yield
    reset_artifact_store()
    reset_task_store()
    reset_deploy_register()


# ── /rollback (pure) ────────────────────────────────────────────────────────


def test_rollback_records_revert_and_note():
    state: PDLCState = {
        "project_id": "proj1",
        "feature": "checkout-v2",
        "version": "v2.1.0",
        "deploy_target": "staging",
        "utility_args": {"to_version": "v2.0.0", "reason": "broken payments"},
    }

    patch = rollback_node(state)

    assert patch["version"] == "v2.0.0"
    result = patch["utility_result"]
    assert result["command"] == "rollback"
    assert result["from_version"] == "v2.1.0"
    assert result["to_version"] == "v2.0.0"
    assert result["env"] == "staging"
    assert result["tier"] == "staging"

    # rollback note artifact persisted and resolvable.
    ref = patch["rollback_ref"]
    note = get_artifact(ref)
    assert "checkout-v2" in note
    assert "v2.0.0" in note
    assert "broken payments" in note

    # a revert deploy was recorded.
    rows = get_deploy_register().list("proj1")
    assert len(rows) == 1
    assert rows[0]["version"] == "v2.0.0"
    assert rows[0]["sha"] == "rollback"
    assert rows[0]["url"] == "https://rollback"
    assert rows[0]["env"] == "staging"


def test_rollback_defaults_when_args_missing():
    patch = rollback_node({"project_id": "p"})
    result = patch["utility_result"]
    assert result["command"] == "rollback"
    assert result["to_version"] == "v0.0.0"
    assert result["env"] == "staging"
    assert get_artifact(patch["rollback_ref"])


# ── /hotfix (interrupt) ─────────────────────────────────────────────────────


def _hotfix_graph():
    g = StateGraph(PDLCState)
    g.add_node("n", hotfix_node)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    return g.compile(checkpointer=MemorySaver())


def test_hotfix_confirm_path():
    c = _hotfix_graph()
    cfg = {"configurable": {"thread_id": "confirm"}}
    init: PDLCState = {
        "project_id": "proj1",
        "feature": "login",
        "version": "v1.2.4",
        "deploy_target": "staging",
        "utility_args": {"summary": "fix login crash"},
    }

    c.invoke(init, cfg)
    # paused at the single confirmation.
    snap = c.get_state(cfg)
    interrupt_val = snap.tasks[0].interrupts[0].value
    assert interrupt_val["mode"] == "hotfix_confirm"
    assert interrupt_val["summary"] == "fix login crash"
    assert interrupt_val["questions"] == ["Confirm emergency hotfix deploy?"]

    out = c.invoke(Command(resume={"confirmed": True}), cfg)
    result = out["utility_result"]
    assert result["command"] == "hotfix"
    assert result["shipped"] is True
    assert result["auto"] is False
    assert result["version"] == "v1.2.4"

    note = get_artifact(out["hotfix_ref"])
    assert "fix login crash" in note
    assert "human-confirmed" in note

    rows = get_deploy_register().list("proj1")
    assert len(rows) == 1
    assert rows[0]["sha"] == "hotfix"
    assert rows[0]["version"] == "v1.2.4"


def test_hotfix_reject_path():
    c = _hotfix_graph()
    cfg = {"configurable": {"thread_id": "reject"}}
    init: PDLCState = {
        "project_id": "proj1",
        "deploy_target": "staging",
        "utility_args": {"summary": "fix nav"},
    }

    c.invoke(init, cfg)
    out = c.invoke(Command(resume={"confirmed": False}), cfg)

    assert out["utility_result"] == {"command": "hotfix", "aborted": True}
    # no deploy recorded, no artifact ref returned.
    assert get_deploy_register().list("proj1") == []
    assert "hotfix_ref" not in out["utility_result"]


def test_hotfix_night_shift_no_interrupt():
    c = _hotfix_graph()
    cfg = {"configurable": {"thread_id": "ns"}}
    init: PDLCState = {
        "project_id": "proj1",
        "feature": "api",
        "version": "v3.0.1",
        "deploy_target": "staging",
        "night_shift_active": True,
        "utility_args": {"summary": "patch api timeout"},
    }

    out = c.invoke(init, cfg)
    # ran to completion — no pause.
    snap = c.get_state(cfg)
    assert snap.tasks == ()

    result = out["utility_result"]
    assert result["shipped"] is True
    assert result["auto"] is True

    note = get_artifact(out["hotfix_ref"])
    assert "night-shift auto-proceed" in note

    rows = get_deploy_register().list("proj1")
    assert len(rows) == 1
    assert rows[0]["version"] == "v3.0.1"


def test_hotfix_night_shift_refuses_production():
    """The layer-2 prod-deploy ban still fires under autonomous flow."""
    c = _hotfix_graph()
    cfg = {"configurable": {"thread_id": "ns-prod"}}
    init: PDLCState = {
        "project_id": "proj1",
        "deploy_target": "production",
        "night_shift_active": True,
        "utility_args": {"summary": "emergency prod patch"},
    }

    with pytest.raises(DeployBanError):
        c.invoke(init, cfg)
    assert get_deploy_register().list("proj1") == []
