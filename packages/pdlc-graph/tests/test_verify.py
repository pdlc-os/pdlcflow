"""Tests for the Operation Verify sub-phase (gate smoke_signoff)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.deploy_port import reset_deploy_register
from pdlc_graph.graphs.ship.verify import GATE_KIND, build_verify
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
        "deploy_target": "staging",
        "deploy_url": "https://app.staging.example",
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
# Happy path — all smoke checks pass, pauses at the sign-off gate
# --------------------------------------------------------------------------- #
def test_happy_path_runs_checks_then_pauses_at_gate():
    g = build_verify().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "happy"}}

    g.invoke(_initial(), cfg)
    gate = _intr(g, cfg)
    assert gate["kind"] == "approval"
    assert gate["gate"] == GATE_KIND
    assert "blocking" not in gate  # all required checks passed

    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["smoke_signed_off"] is True
    res = final["smoke_results"]
    # Security sweep + all three smoke checks recorded.
    assert res["security"]["passed"] is True
    for check in ("http_health", "user_journey", "auth_flow"):
        assert res[check]["passed"] is True
        assert "smoke:" in res[check]["report"]
    # UX verify skipped (no ux_review_ref).
    assert "ux_verify" not in res


# --------------------------------------------------------------------------- #
# UX verify runs only when a UX review exists
# --------------------------------------------------------------------------- #
def test_ux_verify_runs_when_review_ref_present():
    g = build_verify().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ux"}}

    g.invoke(_initial(ux_review_ref="docs/pdlc/design/dark-mode/ux-review.md"), cfg)
    assert _intr(g, cfg)["gate"] == GATE_KIND
    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["smoke_results"]["ux_verify"]["passed"] is True
    assert final["smoke_results"]["ux_verify"]["p0_findings"] == 0


# --------------------------------------------------------------------------- #
# Required smoke failure flags the gate as blocking
# --------------------------------------------------------------------------- #
def test_required_smoke_failure_flags_blocking():
    g = build_verify().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "fail"}}

    g.invoke(_initial(simulate_failing_smoke=["http_health"]), cfg)
    gate = _intr(g, cfg)
    assert gate["gate"] == GATE_KIND
    assert "http_health" in gate["blocking"]

    final = g.invoke(Command(resume={"approved": False}), cfg)
    assert final["smoke_results"]["http_health"]["passed"] is False
    assert final["smoke_signed_off"] is False


# --------------------------------------------------------------------------- #
# Night-shift — runs to completion, auto-approves when nothing blocks
# --------------------------------------------------------------------------- #
def test_night_shift_runs_to_completion_without_interrupt():
    g = build_verify().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}

    out = g.invoke(_initial(night_shift_active=True), cfg)
    assert g.get_state(cfg).next == ()  # ran to completion, no human turn
    assert out["smoke_signed_off"] is True
    assert out["smoke_results"]["http_health"]["passed"] is True


# --------------------------------------------------------------------------- #
# Night-shift refuses when a required smoke check failed (blocking payload)
# --------------------------------------------------------------------------- #
def test_night_shift_refuses_on_required_failure():
    g = build_verify().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns-fail"}}

    out = g.invoke(_initial(night_shift_active=True, simulate_failing_smoke=["user_journey"]), cfg)
    assert g.get_state(cfg).next == ()
    assert out["smoke_signed_off"] is False
