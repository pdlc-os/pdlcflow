"""End-to-end: drive the Construction graph through the REST adapter.

Starts a `/build` command with a seeded task list (as if handed off from
Inception), drives the Strike Panel + review gate via the resolve endpoint, and
asserts the thread completes Construction. Hermetic — same in-memory runtime as
the Inception flow test.
"""

from __future__ import annotations

from uuid import uuid4

from app.main import app
from app.runtime import get_runner
from fastapi.testclient import TestClient

client = TestClient(app)

ORG = str(uuid4())
PROJ = str(uuid4())

_TASKS = [
    {"external_id": "bd-1", "title": "data model", "labels": ["domain:backend"], "depends_on": [], "wave": 1},
    {"external_id": "bd-2", "title": "api", "labels": ["domain:backend"], "depends_on": ["bd-1"], "wave": 2, "simulate_failures": 3},
    {"external_id": "bd-3", "title": "ui", "labels": ["domain:frontend"], "depends_on": ["bd-2"], "wave": 3},
]


def test_build_command_drives_construction_to_completion():
    r = client.post(
        "/v1/commands",
        json={
            "command": "build",
            "org_id": ORG,
            "project_id": PROJ,
            "feature": "dark mode",
            "seed_state": {"tasks": _TASKS},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    thread_id = body["thread_id"]
    pending = body["pending"]

    # First pause is the Strike Panel for bd-2 (3 simulated failures).
    assert pending is not None
    assert pending["payload"]["mode"] == "strike_panel"
    assert pending["payload"]["task_id"] == "bd-2"

    seen_review_gate = False
    steps = 0
    while pending is not None and steps < 20:
        steps += 1
        gid = pending["id"]
        if pending["kind"] == "approval":
            assert pending["gate_kind"] == "review_md_approve"
            seen_review_gate = True
            rr = client.post(f"/v1/approval-gates/{gid}/resolve", json={"approved": True})
        else:
            rr = client.post(f"/v1/approval-gates/{gid}/resolve", json={"answers": ["0"]})
        assert rr.status_code == 200, rr.text
        pending = rr.json()["pending"]

    assert pending is None
    assert seen_review_gate

    snap = get_runner().snapshot(thread_id)
    assert snap["construction_complete"] is True
    assert snap["review_approved"] is True
    assert len(snap["build_log"]) == 3
    assert snap["strike_history"][0]["task_id"] == "bd-2"
