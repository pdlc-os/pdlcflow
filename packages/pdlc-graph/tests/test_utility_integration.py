"""Integration — the utility dispatcher routes by utility_command, and the
meta-graph routes utility commands to the utility subgraph."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.deploy_port import reset_deploy_register
from pdlc_graph.graphs.meta import _route, build_meta_graph
from pdlc_graph.graphs.utility import UTILITY_NODES, build_utility
from pdlc_graph.ports import reset_artifact_store, reset_task_store


@pytest.fixture(autouse=True)
def _hermetic():
    reset_artifact_store()
    reset_task_store()
    reset_deploy_register()
    yield


def test_all_utility_commands_registered():
    assert set(UTILITY_NODES) == {
        "pause", "resume", "abandon", "release", "decide",
        "doctor", "whatif", "override", "rollback", "hotfix",
        "compact",
    }


def test_meta_routes_utility_command_to_utility():
    assert _route({"utility_command": "doctor", "phase": "Operation"}) == "utility"
    # No utility command → normal phase routing.
    assert _route({"phase": "Inception"}) == "brainstorm"


def test_dispatcher_runs_pure_command():
    g = build_utility().compile()
    out = g.invoke({"utility_command": "pause", "feature": "dark mode", "project_id": "p1"})
    assert out["paused"] is True
    assert out["utility_result"]["command"] == "pause"


def test_dispatcher_runs_decide_and_persists_registry():
    g = build_utility().compile()
    out = g.invoke(
        {
            "utility_command": "decide",
            "project_id": "p1",
            "utility_args": {"title": "Use Postgres", "rationale": "atomic claims"},
        }
    )
    assert out["decisions"] and out["decisions"][0]["title"] == "Use Postgres"
    assert out["decisions_ref"]


def test_dispatcher_handles_unknown_command():
    g = build_utility().compile()
    out = g.invoke({"utility_command": "nope", "project_id": "p1"})
    assert out["utility_result"]["error"] == "unknown utility command"


def test_override_interrupt_through_dispatcher():
    g = build_utility().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ovr"}}
    g.invoke(
        {"utility_command": "override", "project_id": "p1", "utility_args": {"reason": "ship blocker"}},
        cfg,
    )
    snap = g.get_state(cfg)
    intr = snap.tasks[0].interrupts[0].value
    assert intr["mode"] == "override_confirm"
    out = g.invoke(Command(resume={"answer": "RED RED"}), cfg)
    assert out["override_log"][0]["confirmed"] is True


def test_meta_graph_drives_a_utility_command():
    g = build_meta_graph(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "m"}}
    out = g.invoke(
        {"utility_command": "doctor", "phase": "Operation", "feature": "dark mode", "project_id": "p1"},
        cfg,
    )
    assert out["doctor_report"] is not None
    assert out["doctor_ref"]
