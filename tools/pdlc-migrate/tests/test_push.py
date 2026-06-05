"""Push client tests — hermetic. ``push_payload`` drives the engine ASGI app
in-process via ``httpx.ASGITransport`` (no network); ``build_import_payload``
is exercised against the bundled sample_project fixture."""

from __future__ import annotations

from pathlib import Path

import app.analytics as analytics
import httpx
import pytest
from app.main import app
from pdlc_migrate.push import build_import_payload, push_payload

FIXTURE = Path(__file__).parent / "fixtures" / "sample_project"

ORG = "00000000-0000-0000-0000-0000000000aa"
PROJ = "00000000-0000-0000-0000-0000000000cc"


@pytest.fixture(autouse=True)
def _fresh_store():
    analytics.reset_analytics_store()
    yield
    analytics.reset_analytics_store()


def _inline_payload() -> dict:
    return {
        "org_id": ORG,
        "project_id": PROJ,
        "taxonomy": {"initiative": "Platform", "application": "acme",
                     "domains": ["frontend"]},
        "memory_files": [
            {"kind": "CONSTITUTION", "path": "x/CONSTITUTION.md", "body": "# c"},
            {"kind": "STATE", "path": "x/STATE.md", "body": "# s"},
        ],
        "tasks": [{"external_id": "bd-1", "title": "t", "labels": [], "status": "done"}],
        "decisions": [{"id": "D-001", "title": "d", "date": "2026-01-11",
                       "rationale": "r"}],
        "deployments": [{"env": "staging", "tier": "staging", "version": "v1",
                         "date": "2026-01-15"}],
        "events": [
            {"event_id": "e1", "event_type": "phase.entered",
             "ts": "2026-01-10T09:00:00+00:00", "roadmap_id": "F-001",
             "user_story_id": None, "payload": {"phase": "Inception", "synthetic": True}},
        ],
    }


def test_push_payload_posts_to_engine_via_asgi_transport():
    transport = httpx.ASGITransport(app=app)
    result = push_payload(_inline_payload(), "http://engine", transport=transport)
    assert result == {
        "events": 1,
        "memory_files": 2,
        "tasks": 1,
        "decisions": 1,
        "deployments": 1,
    }


def test_push_payload_is_idempotent_on_events():
    transport = httpx.ASGITransport(app=app)
    first = push_payload(_inline_payload(), "http://engine", transport=transport)
    assert first["events"] == 1
    second = push_payload(_inline_payload(), "http://engine", transport=transport)
    assert second["events"] == 0  # deterministic event_id dedups the re-run


def test_build_import_payload_from_fixture_is_pure():
    events = [
        {"event_id": "syn-1", "event_type": "deploy.succeeded",
         "ts": "2026-01-15T11:00:00+00:00", "roadmap_id": "F-001",
         "user_story_id": None, "payload": {"version": "v1.1.0", "synthetic": True}},
    ]
    payload = build_import_payload(
        FIXTURE,
        org_id=ORG,
        project_id=PROJ,
        taxonomy={"initiative": "Platform", "application": "acme",
                  "domains": ["frontend", "devops"]},
        events=events,
    )

    assert payload["org_id"] == ORG
    assert payload["project_id"] == PROJ
    assert payload["taxonomy"]["domains"] == ["frontend", "devops"]
    # All 9 memory files (8 standard + DEPLOYMENTS.md), bodies read off disk.
    kinds = {mf["kind"] for mf in payload["memory_files"]}
    assert {"CONSTITUTION", "STATE", "DECISIONS", "DEPLOYMENTS"} <= kinds
    assert len(payload["memory_files"]) == 9
    assert all(mf["body"] for mf in payload["memory_files"])
    assert payload["events"] == events


def test_build_import_payload_round_trips_through_engine():
    payload = build_import_payload(
        FIXTURE,
        org_id=ORG,
        project_id=PROJ,
        taxonomy={"initiative": None, "application": None, "domains": []},
        events=[
            {"event_id": "rt-1", "event_type": "session.opened",
             "ts": "2026-01-10T08:00:00+00:00", "roadmap_id": None,
             "user_story_id": None, "payload": {"synthetic": True}},
        ],
    )
    transport = httpx.ASGITransport(app=app)
    result = push_payload(payload, "http://engine", transport=transport)
    assert result["events"] == 1
    assert result["memory_files"] == 9
