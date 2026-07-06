"""Migration import endpoint tests — drive POST /v1/migrate/import via
TestClient and assert ingest counts, idempotency, and queryability."""

from __future__ import annotations

from uuid import UUID

import app.analytics as analytics
import pytest
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

ORG = "00000000-0000-0000-0000-0000000000aa"
PROJ = "00000000-0000-0000-0000-0000000000cc"


def _payload() -> dict:
    return {
        "org_id": ORG,
        "project_id": PROJ,
        "taxonomy": {
            "initiative": "Platform",
            "application": "acme-app",
            "domains": ["frontend", "devops"],
        },
        "memory_files": [
            {"kind": "CONSTITUTION", "path": "docs/CONSTITUTION.md", "body": "# rules"},
            {"kind": "STATE", "path": "docs/STATE.md", "body": "# state"},
        ],
        "tasks": [
            {"external_id": "bd-1", "title": "t1", "labels": ["x"], "status": "done"},
        ],
        "decisions": [
            {"id": "D-001", "title": "use css vars", "date": "2026-01-11",
             "rationale": "tokens"},
        ],
        "deployments": [
            {"env": "staging", "tier": "staging", "version": "v1.1.0",
             "date": "2026-01-15"},
        ],
        "events": [
            {
                "event_id": "evt-phase-entered-1",
                "event_type": "phase.entered",
                "ts": "2026-01-10T09:00:00+00:00",
                "roadmap_id": "F-001",
                "user_story_id": None,
                "payload": {"phase": "Inception", "synthetic": True},
            },
            {
                "event_id": "evt-deploy-1",
                "event_type": "deploy.succeeded",
                "ts": "2026-01-15T11:00:00+00:00",
                "roadmap_id": "F-001",
                "user_story_id": None,
                "payload": {"version": "v1.1.0", "synthetic": True},
            },
        ],
    }


@pytest.fixture(autouse=True)
def _fresh_store():
    from pdlc_graph.ports import reset_artifact_store, reset_task_store

    analytics.reset_analytics_store()
    reset_task_store()
    reset_artifact_store()
    yield
    analytics.reset_analytics_store()
    reset_task_store()
    reset_artifact_store()


def test_import_persists_everything_and_reports_received_vs_persisted():
    r = client.post("/v1/migrate/import", json=_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    # Per-kind top-level counts are now PERSISTED counts (were len() echoes).
    assert body["events"] == 2
    assert body["memory_files"] == 2
    assert body["tasks"] == 1
    assert body["decisions"] == 1
    assert body["deployments"] == 1
    # received block mirrors the input so partial support can't masquerade.
    assert body["received"] == {
        "events": 2, "memory_files": 2, "tasks": 1, "decisions": 1, "deployments": 1}
    # entities: DB-gated — no Postgres in the hermetic suite → None (not a crash).
    assert body["entities"] == {"initiative_id": None, "application_id": None}


def test_import_actually_writes_tasks_decisions_deployments():
    from pdlc_graph.ports import get_artifact, get_task_store

    client.post("/v1/migrate/import", json=_payload())

    # Task landed in the durable store with its external_id preserved.
    assert "bd-1" in get_task_store()._tasks  # in-memory store keys by external_id
    # Decision + deployment artifacts written under the org/project namespace.
    base = f"memory://{ORG}/{PROJ}"
    decisions = get_artifact(f"{base}/docs/pdlc/memory/DECISIONS.md")
    assert "use css vars" in decisions
    deployments = get_artifact(f"{base}/docs/pdlc/memory/DEPLOYMENTS.md")
    assert "staging" in deployments and "v1.1.0" in deployments


def test_second_identical_import_ingests_zero_events():
    first = client.post("/v1/migrate/import", json=_payload()).json()
    assert first["events"] == 2

    totals_after_first = analytics.get_analytics_store().totals(org_id=ORG)["events"]

    second = client.post("/v1/migrate/import", json=_payload()).json()
    assert second["events"] == 0

    totals_after_second = analytics.get_analytics_store().totals(org_id=ORG)["events"]
    assert totals_after_first == totals_after_second == 2


def test_imported_events_are_queryable_via_live():
    client.post("/v1/migrate/import", json=_payload())

    r = client.get("/v1/admin/live", params={"org_id": ORG})
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) == 2
    types = {e["event_type"] for e in events}
    assert types == {"phase.entered", "deploy.succeeded"}
    assert all(e["org_id"] == ORG for e in events)
    # Deterministic uuid5 ids — stable across runs.
    assert all(UUID(e["event_id"]) for e in events)
