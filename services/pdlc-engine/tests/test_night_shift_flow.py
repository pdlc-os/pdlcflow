"""End-to-end: the /night-shift autonomous run through the REST adapter.

The Contract Party is the only human gate; after approval the run builds and
ships autonomously under the Sentinel. Hermetic.
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
    "tasks": [
        {"external_id": "bd-1", "title": "data model", "labels": ["domain:backend"], "depends_on": [], "wave": 1},
        {"external_id": "bd-2", "title": "api", "labels": ["domain:backend"], "depends_on": ["bd-1"], "wave": 2},
    ],
    "commits": ["feat: dark mode"],
    "deploy_candidates": ["staging", "prod-eu"],
}


def test_night_shift_contract_then_autonomous_completion():
    r = client.post(
        "/v1/commands",
        json={"command": "night-shift", "org_id": ORG, "project_id": PROJ,
              "feature": "dark mode", "seed_state": _SEED},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    pending = body["pending"]
    # The single human gate is the Contract Party.
    assert pending is not None
    assert pending["gate_kind"] == "night_shift_contract"

    rr = client.post(f"/v1/approval-gates/{pending['id']}/resolve", json={"approved": True})
    assert rr.status_code == 200, rr.text
    assert rr.json()["pending"] is None  # ran autonomously to completion

    snap = get_runner().snapshot(body["thread_id"])
    assert snap["night_shift_outcome"] == "completed"
    assert snap["construction_complete"] is True
    assert snap["operation_complete"] is True
    assert snap["deploy_tier"] != "production"  # prod candidate filtered out


def test_night_shift_decline_ends_the_run():
    r = client.post(
        "/v1/commands",
        json={"command": "night-shift", "org_id": ORG, "project_id": PROJ,
              "feature": "dark mode", "seed_state": _SEED},
    )
    pending = r.json()["pending"]
    rr = client.post(f"/v1/approval-gates/{pending['id']}/resolve", json={"approved": False})
    assert rr.status_code == 200
    snap = get_runner().snapshot(r.json()["thread_id"])
    assert snap["night_shift_outcome"] == "declined"
