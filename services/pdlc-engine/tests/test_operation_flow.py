"""End-to-end: drive the Operation graph through the REST adapter.

Starts a `/ship` command with seeded state (as if handed off from Construction),
walks the three Operation gates (merge_and_deploy / smoke_signoff / episode) via
the resolve endpoint, and asserts the thread completes Operation. Hermetic.
"""

from __future__ import annotations

from uuid import uuid4

from app.main import app
from app.runtime import get_runner
from fastapi.testclient import TestClient

client = TestClient(app)

ORG = str(uuid4())
PROJ = str(uuid4())

_SEED = {
    "version": "v1.2.3",
    "commits": ["feat: ship it"],
    "deploy_candidates": ["staging", "prod-eu"],
    "build_log": [{"task_id": "bd-1", "status": "done"}],
    "construction_test_results": {"unit": {"passed": True}},
    "review_ref": "memory://p/reviews/REVIEW.md",
}


def test_ship_command_drives_operation_to_completion():
    r = client.post(
        "/v1/commands",
        json={
            "command": "ship",
            "org_id": ORG,
            "project_id": PROJ,
            "feature": "dark mode",
            "seed_state": _SEED,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    thread_id = body["thread_id"]
    pending = body["pending"]
    assert pending is not None
    assert pending["gate_kind"] == "merge_and_deploy_approve"

    gates_seen = []
    steps = 0
    while pending is not None and steps < 12:
        steps += 1
        gid = pending["id"]
        if pending["kind"] == "approval":
            gates_seen.append(pending["gate_kind"])
            rr = client.post(f"/v1/approval-gates/{gid}/resolve", json={"approved": True})
        else:
            rr = client.post(f"/v1/approval-gates/{gid}/resolve", json={"answers": ["ok"]})
        assert rr.status_code == 200, rr.text
        pending = rr.json()["pending"]

    assert pending is None
    assert gates_seen == ["merge_and_deploy_approve", "smoke_signoff", "episode_approve"]

    snap = get_runner().snapshot(thread_id)
    assert snap["operation_complete"] is True
    assert snap["merged"] is True
    assert snap["version"] == "v1.3.0"  # minor bump from the feat commit
    assert snap["deploy_tier"] != "production"  # prod candidate filtered out
    assert snap["episode_ref"] and snap["metrics_ref"]
