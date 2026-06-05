"""Integration test — the full Operation graph (Ship → Verify → Reflect).

Proves the three segments compose under one parent and that `interrupt()` sites
propagate to the top-level checkpointer. Night-shift drives the whole chain to
completion; a human-path test walks the three gates in order.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.deploy_port import get_deploy_register, reset_deploy_register
from pdlc_graph.graphs.ship import build_operation
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


def _initial(**over) -> dict:
    base = {
        "feature": "dark mode",
        "project_id": "p1",
        "version": "v1.2.3",
        "commits": ["feat: add dark mode toggle"],
        "deploy_candidates": ["staging", "prod-us-east"],
        "build_log": [{"task_id": "bd-1", "status": "done"}],
        "construction_test_results": {"unit": {"passed": True}},
        "review_ref": "memory://p1/reviews/REVIEW.md",
    }
    base.update(over)
    return base


def _intr(g, cfg):
    snap = g.get_state(cfg)
    for task in snap.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    raise AssertionError("expected a pending interrupt but none was found")


def test_night_shift_runs_all_three_segments():
    g = build_operation().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}

    out = g.invoke(_initial(night_shift_active=True), cfg)
    assert g.get_state(cfg).next == ()  # ran to completion

    # Ship: production candidate dropped, minor bump from the feat commit.
    assert out["merge_and_deploy_approved"] is True
    assert out["merged"] is True
    assert out["version"] == "v1.3.0"
    assert out["deploy_tier"] != "production"
    assert out["deploy_url"] and out["deployments_ref"]
    # Verify + Reflect.
    assert out["smoke_signed_off"] is True
    assert out["episode_approved"] is True
    assert out["episode_ref"] and out["metrics_ref"]
    assert out["operation_complete"] is True

    # Deployment was registered (to a non-prod tier).
    rows = get_deploy_register().list("p1")
    assert len(rows) == 1 and rows[0]["tier"] != "production"


def test_human_path_walks_three_gates_in_order():
    g = build_operation().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "human"}}

    g.invoke(_initial(), cfg)
    gates_seen = []
    pending = _intr(g, cfg)
    steps = 0
    while steps < 12:
        steps += 1
        if pending.get("kind") == "approval":
            gates_seen.append(pending["gate"])
        g.invoke(Command(resume={"approved": True}), cfg)
        snap = g.get_state(cfg)
        if not snap.next:
            break
        nxt = None
        for task in snap.tasks:
            if task.interrupts:
                nxt = task.interrupts[0].value
                break
        if nxt is None:
            break
        pending = nxt

    assert gates_seen == [
        "merge_and_deploy_approve",
        "smoke_signoff",
        "episode_approve",
    ]
    final = g.get_state(cfg).values
    assert final["operation_complete"] is True
