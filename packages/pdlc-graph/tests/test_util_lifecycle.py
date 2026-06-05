"""Tests for the lifecycle utility nodes: pause, resume, abandon, release.

All four are pure nodes (no interrupt), so we call them directly and assert the
returned state patch. A night-shift case is included for each to confirm they
run to completion without pausing for human confirmation (none of them call
``interrupt()``).
"""

from __future__ import annotations

import pytest
from pdlc_graph.graphs.utility.abandon import abandon_node
from pdlc_graph.graphs.utility.pause import pause_node
from pdlc_graph.graphs.utility.release import release_node
from pdlc_graph.graphs.utility.resume import resume_node
from pdlc_graph.ports import (
    reset_artifact_store,
    reset_task_store,
)


@pytest.fixture(autouse=True)
def _hermetic() -> None:
    reset_artifact_store()
    reset_task_store()


# ── pause ────────────────────────────────────────────────────────────────
def test_pause_sets_flag_and_checkpoint() -> None:
    patch = pause_node(
        {
            "feature": "user-auth",
            "phase": "Construction",
            "sub_phase": "wave-1",
        }
    )
    assert patch["paused"] is True
    res = patch["utility_result"]
    assert res["command"] == "pause"
    assert res["paused"] is True
    assert res["feature"] == "user-auth"
    # checkpoint note recorded in both the patch and the result summary
    assert "Paused" in patch["last_checkpoint"]
    assert res["checkpoint"] == patch["last_checkpoint"]
    assert res["phase"] == "Construction"


def test_pause_night_shift_runs_to_completion() -> None:
    patch = pause_node(
        {
            "feature": "webhooks",
            "phase": "Operation",
            "night_shift_active": True,
        }
    )
    assert patch["paused"] is True
    assert patch["utility_result"]["feature"] == "webhooks"


# ── resume ───────────────────────────────────────────────────────────────
def test_resume_clears_flag() -> None:
    patch = resume_node(
        {
            "feature": "user-auth",
            "phase": "Construction",
            "sub_phase": "wave-1",
            "paused": True,
            "last_checkpoint": "Paused / Construction / 2026-06-01T00:00:00+00:00",
        }
    )
    assert patch["paused"] is False
    res = patch["utility_result"]
    assert res["command"] == "resume"
    assert res["resumed"] is True
    assert res["paused"] is False
    assert res["feature"] == "user-auth"
    assert res["from_checkpoint"] == "Paused / Construction / 2026-06-01T00:00:00+00:00"
    assert "Resumed" in patch["last_checkpoint"]


def test_resume_night_shift_runs_to_completion() -> None:
    patch = resume_node(
        {
            "feature": "webhooks",
            "phase": "Operation",
            "paused": True,
            "night_shift_active": True,
        }
    )
    assert patch["paused"] is False
    assert patch["utility_result"]["resumed"] is True


# ── abandon ──────────────────────────────────────────────────────────────
def test_abandon_marks_and_drops_claim() -> None:
    patch = abandon_node(
        {
            "feature": "legacy-import",
            "phase": "Inception",
            "sub_phase": "discover",
            "roadmap_claim": {"feature_id": "F-007", "claimed_by": "me"},
            "utility_args": {"reason": "no longer viable"},
        }
    )
    assert patch["abandoned"] is True
    assert patch["roadmap_claim"] is None
    res = patch["utility_result"]
    assert res["command"] == "abandon"
    assert res["abandoned"] is True
    assert res["feature"] == "legacy-import"
    assert res["reason"] == "no longer viable"
    # artifacts are NOT deleted
    assert res["artifacts_preserved"] is True


def test_abandon_uses_args_feature_override() -> None:
    patch = abandon_node(
        {
            "feature": "active-one",
            "utility_args": {"feature": "other-feature", "reason": "dup"},
        }
    )
    assert patch["utility_result"]["feature"] == "other-feature"


def test_abandon_night_shift_runs_to_completion() -> None:
    patch = abandon_node(
        {
            "feature": "webhooks",
            "phase": "Construction",
            "night_shift_active": True,
            "utility_args": {"reason": "auto-abandon"},
        }
    )
    assert patch["abandoned"] is True
    assert patch["roadmap_claim"] is None


# ── release ──────────────────────────────────────────────────────────────
def test_release_drops_held_claim_and_reports_it() -> None:
    held = {"feature_id": "F-005", "claimed_by": "alice@example.com"}
    patch = release_node(
        {
            "roadmap_claim": held,
            "utility_args": {"reason": "dev left the team"},
        }
    )
    assert patch["roadmap_claim"] is None
    res = patch["utility_result"]
    assert res["command"] == "release"
    assert res["released"] is True
    assert res["released_claim"] == held
    assert res["feature_id"] == "F-005"
    assert res["reason"] == "dev left the team"


def test_release_no_claim_held() -> None:
    patch = release_node({"roadmap_claim": None})
    assert patch["roadmap_claim"] is None
    res = patch["utility_result"]
    assert res["released_claim"] is None
    assert res["feature_id"] is None
    assert "nothing to release" in res["note"].lower()


def test_release_night_shift_runs_to_completion() -> None:
    patch = release_node(
        {
            "roadmap_claim": {"feature_id": "F-009"},
            "night_shift_active": True,
            "utility_args": {"reason": "stuck"},
        }
    )
    assert patch["roadmap_claim"] is None
    assert patch["utility_result"]["feature_id"] == "F-009"
