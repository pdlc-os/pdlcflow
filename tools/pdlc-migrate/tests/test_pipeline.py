"""Pipeline tests — scan parsers + backfill + taxonomy against the fixture."""

from __future__ import annotations

from pathlib import Path

from event_schema.envelope import EVENT_TYPES
from pdlc_migrate.backfill import backfill_events
from pdlc_migrate.scan import (
    parse_decisions,
    parse_deployments,
    parse_phase_history,
    parse_roadmap,
    parse_tasks,
    read_memory_files,
    scan_project,
)
from pdlc_migrate.taxonomy import assign_taxonomy_core

FIXTURE = Path(__file__).parent / "fixtures" / "sample_project"


# --------------------------------------------------------------------------- #
# scan parsers
# --------------------------------------------------------------------------- #

def test_parse_decisions():
    decisions = parse_decisions(FIXTURE)
    assert len(decisions) == 2
    assert decisions[0] == {
        "id": "D-001",
        "title": "Use CSS custom properties for theming",
        "date": "2026-01-11",
        "rationale": "Tokens let tenants re-skin without code changes.",
    }
    assert decisions[1]["id"] == "D-002"
    assert decisions[1]["date"] == "2026-01-12"


def test_parse_tasks():
    tasks = parse_tasks(FIXTURE)
    assert len(tasks) == 4
    assert [t["external_id"] for t in tasks] == ["bd-1", "bd-2", "bd-3", "bd-4"]
    assert tasks[0]["title"] == "Theme token CSS variables"
    assert tasks[0]["status"] == "done"
    assert "domain:frontend" in tasks[0]["labels"]


def test_parse_deployments():
    deps = parse_deployments(FIXTURE)
    assert len(deps) == 1
    assert deps[0] == {
        "env": "staging",
        "tier": "staging",
        "version": "v1.1.0",
        "date": "2026-01-15",
    }


def test_parse_phase_history():
    rows = parse_phase_history(FIXTURE)
    assert len(rows) == 6
    assert rows[0] == {
        "ts": "2026-01-10T09:00:00Z",
        "event": "inception_start",
        "phase": "Inception",
        "sub_phase": "Discover",
        "feature": "dark-mode",
    }
    assert rows[-1]["event"] == "operation_complete"
    assert rows[-1]["feature"] == "none"


def test_parse_roadmap():
    mapping = parse_roadmap(FIXTURE)
    assert mapping["dark-mode"] == "F-001"
    assert mapping["saved-searches"] == "F-002"


def test_read_memory_files():
    files = read_memory_files(FIXTURE)
    kinds = {f["kind"] for f in files}
    assert {"CONSTITUTION", "STATE", "DECISIONS", "ROADMAP", "DEPLOYMENTS"} <= kinds
    const = next(f for f in files if f["kind"] == "CONSTITUTION")
    assert const["body"].startswith("# Constitution")
    assert const["path"].endswith("CONSTITUTION.md")


def test_scan_summary_contract_intact():
    # parsers must not disturb the existing scan_project summary contract.
    summary = scan_project(FIXTURE).summary
    assert summary["bd_tasks"] == 4
    assert summary["deployments"] == 1
    assert set(summary) == {
        "memory_files", "episodes", "bd_tasks", "deployments", "night_shift_runs",
    }


# --------------------------------------------------------------------------- #
# backfill
# --------------------------------------------------------------------------- #

def test_backfill_event_count_and_types():
    events = backfill_events(FIXTURE)
    # 6 phase-history rows + 2 decisions.
    assert len(events) == 8
    types = [e["event_type"] for e in events]
    assert types[:6] == [
        "phase.entered",     # inception_start
        "subphase.entered",  # prd_approved
        "phase.entered",     # construction_start
        "subphase.entered",  # review_approved
        "deploy.succeeded",  # deploy_succeeded
        "session.closed",    # operation_complete
    ]
    assert types[6:] == ["decision.recorded", "decision.recorded"]


def test_backfill_all_events_valid_and_synthetic():
    for ev in backfill_events(FIXTURE):
        assert ev["event_type"] in EVENT_TYPES
        assert ev["payload"]["synthetic"] is True
        assert ev.get("event_id")
        assert "ts" in ev


def test_backfill_roadmap_id_mapped():
    events = backfill_events(FIXTURE)
    dark = next(e for e in events if e["event_type"] == "deploy.succeeded")
    assert dark["roadmap_id"] == "F-001"
    # decision events carry no roadmap_id.
    dec = next(e for e in events if e["event_type"] == "decision.recorded")
    assert dec["roadmap_id"] is None


def test_backfill_is_deterministic():
    first = backfill_events(FIXTURE)
    second = backfill_events(FIXTURE)
    assert first == second
    assert [e["event_id"] for e in first] == [e["event_id"] for e in second]


# --------------------------------------------------------------------------- #
# taxonomy
# --------------------------------------------------------------------------- #

def test_taxonomy_core_explicit_values():
    result = assign_taxonomy_core(
        FIXTURE,
        initiative="Platform",
        application="Acme App",
        domains=["frontend", "frontend", "devops"],
    )
    assert result == {
        "initiative": "Platform",
        "application": "Acme App",
        "domains": ["devops", "frontend"],
    }


def test_taxonomy_core_derives_domains_from_tasks():
    result = assign_taxonomy_core(
        FIXTURE, initiative=None, application=None, domains=None
    )
    assert result["initiative"] is None
    assert result["domains"] == ["devops", "frontend"]


def test_taxonomy_core_accepts_manifest():
    manifest = scan_project(FIXTURE)
    result = assign_taxonomy_core(
        manifest, initiative="I", application="A", domains=["x"]
    )
    assert result == {"initiative": "I", "application": "A", "domains": ["x"]}
