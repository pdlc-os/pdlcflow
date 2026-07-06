"""Tests for the Ship segment of the Operation loop (gate merge_and_deploy_approve)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.deploy_port import get_deploy_register, reset_deploy_register
from pdlc_graph.graphs.ship.ship import GATE_KIND, build_ship
from pdlc_graph.ports import get_artifact, reset_artifact_store, reset_task_store
from pdlc_graph.render import render_changelog, render_deployments
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
        "commits": ["feat: add dark mode", "fix: contrast"],
        "deploy_candidates": ["staging"],
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
def test_render_changelog_conventional_headings():
    md = render_changelog(
        version="v1.3.0",
        date="2026-06-05",
        added=["new feature"],
        changed=["tweaked"],
        fixed=["bug"],
        breaking=["dropped API"],
    )
    assert "## v1.3.0 — 2026-06-05" in md
    for heading in ("### Added", "### Changed", "### Fixed", "### Breaking Changes"):
        assert heading in md
    assert "- new feature" in md


def test_render_changelog_omits_empty_sections():
    md = render_changelog(version="v0.1.0", date="2026-06-05", added=["only this"])
    assert "### Added" in md
    assert "### Changed" not in md
    assert "### Breaking Changes" not in md


def test_render_deployments_has_tier_and_history():
    md = render_deployments(
        feature="dark mode",
        env="staging",
        tier="staging",
        version="v1.3.0",
        url="https://dark-mode.example.app",
        sha="abc123",
        date="2026-06-05",
    )
    assert "### Environment: staging" in md
    assert "| tier | staging |" in md
    assert "#### Deployment History" in md
    assert "v1.3.0" in md and "abc123" in md


# --------------------------------------------------------------------------- #
# Happy path — pause at the gate, approve, merge + deploy
# --------------------------------------------------------------------------- #
def test_happy_path_pauses_then_merges_and_deploys():
    g = build_ship().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "happy"}}

    g.invoke(_initial(), cfg)
    gate = _intr(g, cfg)
    assert gate["kind"] == "approval"
    assert gate["gate"] == GATE_KIND
    # feat + fix -> minor bump from v1.2.3
    assert gate["version"] == "v1.3.0"
    assert gate["deploy_target"] == "staging"
    assert gate["deploy_tier"] == "staging"
    assert gate["changelog_ref"]

    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["merge_and_deploy_approved"] is True
    assert final["merged"] is True
    assert final["version"] == "v1.3.0"
    # No deployer wired (hermetic) -> honest simulated placeholder, not a fake URL.
    assert "simulated" in final["deploy_url"]
    assert "example.app" not in final["deploy_url"]
    assert final["deployments_ref"]

    # CHANGELOG + DEPLOYMENTS are real rendered markdown.
    assert "## v1.3.0" in get_artifact(final["changelog_ref"])
    assert "### Environment: staging" in get_artifact(final["deployments_ref"])

    # Deploy register has one row for this project.
    rows = get_deploy_register().list("p1")
    assert len(rows) == 1
    assert rows[0]["env"] == "staging"
    assert rows[0]["version"] == "v1.3.0"


# --------------------------------------------------------------------------- #
# Rejection — human declines; nothing merges
# --------------------------------------------------------------------------- #
def test_rejection_does_not_merge_or_deploy():
    g = build_ship().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "reject"}}

    g.invoke(_initial(), cfg)
    assert _intr(g, cfg)["gate"] == GATE_KIND

    final = g.invoke(Command(resume={"approved": False}), cfg)
    assert final["merge_and_deploy_approved"] is False
    assert final.get("merged") is False
    assert final.get("deployments_ref") is None
    assert get_deploy_register().list("p1") == []


# --------------------------------------------------------------------------- #
# Production candidate is filtered out at selection (layer 1 of the ban)
# --------------------------------------------------------------------------- #
def test_production_candidate_is_dropped():
    g = build_ship().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "prod"}}

    g.invoke(_initial(deploy_candidates=["production", "staging"]), cfg)
    gate = _intr(g, cfg)
    assert gate["deploy_target"] == "staging"
    assert gate["deploy_tier"] == "staging"


# --------------------------------------------------------------------------- #
# Night-shift — no human turns, runs to completion auto-approved
# --------------------------------------------------------------------------- #
def test_night_shift_runs_to_completion_without_interrupt():
    g = build_ship().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}

    out = g.invoke(_initial(night_shift_active=True), cfg)
    assert g.get_state(cfg).next == ()  # ran to completion
    assert out["merge_and_deploy_approved"] is True
    assert out["merged"] is True
    assert out["version"] == "v1.3.0"
    assert out["deploy_url"]
    assert len(get_deploy_register().list("p1")) == 1
