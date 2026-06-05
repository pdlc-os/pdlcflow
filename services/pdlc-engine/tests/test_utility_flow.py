"""End-to-end: utility commands through the REST adapter.

A pure utility (/doctor) runs to completion in one call; an interrupting one
(/override) pauses and resumes via the resolve endpoint. Hermetic.
"""

from __future__ import annotations

from uuid import uuid4

from app.main import app
from app.runtime import get_runner
from fastapi.testclient import TestClient

client = TestClient(app)

ORG = str(uuid4())
PROJ = str(uuid4())


def _invoke(command: str, **extra):
    body = {"command": command, "org_id": ORG, "project_id": PROJ, **extra}
    r = client.post("/v1/commands", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_doctor_runs_to_completion():
    body = _invoke("doctor", feature="dark mode")
    assert body["started"] is True
    assert body["pending"] is None  # pure utility — no gate
    snap = get_runner().snapshot(body["thread_id"])
    assert snap["doctor_report"] is not None
    assert snap["doctor_ref"]
    assert snap["utility_result"]["command"] == "doctor"


def test_pause_sets_state():
    body = _invoke("pause", feature="dark mode")
    snap = get_runner().snapshot(body["thread_id"])
    assert snap["paused"] is True


def test_override_pauses_then_confirms_via_resolve():
    body = _invoke("override", seed_state={"utility_args": {"reason": "ship blocker"}})
    pending = body["pending"]
    assert pending is not None
    assert pending["payload"]["mode"] == "override_confirm"

    rr = client.post(
        f"/v1/approval-gates/{pending['id']}/resolve",
        json={"answers": ["RED RED"]},
    )
    assert rr.status_code == 200, rr.text
    assert rr.json()["pending"] is None
    snap = get_runner().snapshot(body["thread_id"])
    assert snap["override_log"][0]["confirmed"] is True
