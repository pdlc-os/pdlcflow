"""Tests for the Night-Shift runtime (preflight → contract → build/ship → sentinel)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.deploy_port import get_deploy_register, reset_deploy_register
from pdlc_graph.graphs.night_shift import build_night_shift
from pdlc_graph.ports import reset_artifact_store, reset_task_store
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


def _saver():
    return build_night_shift(checkpointer=MemorySaver())


def _tasks() -> list[dict]:
    return [
        {"external_id": "bd-1", "title": "data model", "labels": ["domain:backend"], "depends_on": [], "wave": 1},
        {"external_id": "bd-2", "title": "api", "labels": ["domain:backend"], "depends_on": ["bd-1"], "wave": 2},
    ]


def _initial(**over) -> dict:
    base = {
        "feature": "dark mode",
        "project_id": "p1",
        "tasks": _tasks(),
        "commits": ["feat: dark mode"],
        "deploy_candidates": ["staging", "prod-us-east"],
        "night_shift_active": True,
        "night_shift_run_id": "ns-1",
    }
    base.update(over)
    return base


def _contract(g, cfg):
    snap = g.get_state(cfg)
    for task in snap.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    raise AssertionError("expected the contract-party interrupt")


def test_happy_path_one_human_gate_then_autonomous_completion():
    g = _saver()
    cfg = {"configurable": {"thread_id": "ns"}}

    g.invoke(_initial(), cfg)
    contract = _contract(g, cfg)  # the ONLY pause
    assert contract["gate"] == "night_shift_contract"

    out = g.invoke(Command(resume={"approved": True}), cfg)
    assert g.get_state(cfg).next == ()  # ran autonomously to the end
    assert out["night_shift_outcome"] == "completed"
    assert out["construction_complete"] is True
    assert out["operation_complete"] is True
    assert out["version"].startswith("v")
    assert out["deploy_tier"] != "production"  # prod candidate filtered out
    assert get_deploy_register().list("p1")[0]["tier"] != "production"


def test_declining_the_contract_ends_the_run():
    g = _saver()
    cfg = {"configurable": {"thread_id": "decline"}}
    g.invoke(_initial(), cfg)
    out = g.invoke(Command(resume={"approved": False}), cfg)
    assert out["night_shift_outcome"] == "declined"
    assert out.get("operation_complete") is not True


def test_preflight_aborts_without_tasks_and_never_reaches_contract():
    g = _saver()
    cfg = {"configurable": {"thread_id": "pre"}}
    out = g.invoke(_initial(tasks=[]), cfg)
    assert g.get_state(cfg).next == ()  # no contract interrupt — aborted at preflight
    assert out["night_shift_outcome"] == "aborted"
    assert "preflight" in out["night_shift_abort_reason"]


def test_production_target_is_refused_at_preflight():
    g = _saver()
    cfg = {"configurable": {"thread_id": "prod"}}
    out = g.invoke(_initial(target_environment="prod-us-east"), cfg)
    assert out["night_shift_outcome"] == "aborted"
    assert "production" in out["night_shift_abort_reason"]


def test_sentinel_aborts_the_run_on_a_marker():
    g = _saver()
    cfg = {"configurable": {"thread_id": "sent"}}
    g.invoke(_initial(ns_markers=["ns-abort:critical-security"]), cfg)
    out = g.invoke(Command(resume={"approved": True}), cfg)
    assert out["night_shift_outcome"] == "aborted"
    assert out["night_shift_abort_reason"] == "critical-security"
