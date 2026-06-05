"""End-to-end: drive the real Inception graph through the REST + WS adapters.

No external services — MemorySaver checkpointer, in-memory gate store + event
bus, and pdlc-graph's offline LLM stub. Proves command → gate/question →
resolve → resume cycles all the way through Discover/Define/Design/Plan.
"""

from __future__ import annotations

from uuid import uuid4

from app.main import app
from app.runtime import get_runner
from fastapi.testclient import TestClient

client = TestClient(app)

ORG = str(uuid4())
PROJ = str(uuid4())


def _start_brainstorm(mode: str = "socratic") -> dict:
    r = client.post(
        "/v1/commands",
        json={
            "command": "brainstorm",
            "org_id": ORG,
            "project_id": PROJ,
            "feature": "saved searches",
            "interaction_mode": mode,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_command_starts_graph_and_opens_first_interaction():
    body = _start_brainstorm()
    assert body["started"] is True
    assert body["thread_id"].startswith(f"{ORG}:{PROJ}:")
    pending = body["pending"]
    assert pending is not None
    assert pending["kind"] == "user_input_required"
    assert pending["payload"]["questions"]  # a Socratic round


def test_open_gates_are_listed_and_scoped_by_project():
    body = _start_brainstorm()
    gates = client.get(f"/v1/approval-gates?project_id={PROJ}").json()
    assert any(g["id"] == body["pending"]["id"] for g in gates)
    # A different project sees none of them.
    assert client.get(f"/v1/approval-gates?project_id={uuid4()}").json() == []


def test_full_inception_loop_resolves_every_gate_to_completion():
    body = _start_brainstorm()
    thread_id = body["thread_id"]
    pending = body["pending"]

    gate_kinds: list[str] = []
    steps = 0
    while pending is not None and steps < 40:
        steps += 1
        gid = pending["id"]
        if pending["kind"] == "approval":
            gate_kinds.append(pending["gate_kind"])
            rr = client.post(f"/v1/approval-gates/{gid}/resolve", json={"approved": True})
        else:
            n = len(pending["payload"].get("questions") or [])
            rr = client.post(
                f"/v1/approval-gates/{gid}/resolve",
                json={"answers": [f"answer-{i}" for i in range(n)]},
            )
        assert rr.status_code == 200, rr.text
        pending = rr.json()["pending"]

    assert pending is None, "thread did not reach completion"
    assert steps < 40

    # All four Inception gates were traversed, in order.
    assert gate_kinds == [
        "discover_summary",
        "prd_approve",
        "design_docs_approve",
        "beads_tasklist_approve",
    ]

    # Final graph state carries every sub-phase's output.
    snap = get_runner().snapshot(thread_id)
    assert snap["prd_approved"] is True
    assert snap["design_approved"] is True
    assert snap["plan_approved"] is True
    assert snap["prd_ref"] and snap["plan_ref"]
    assert snap["handoff"]["next_phase"] == "Construction / Build"


def test_resolving_unknown_gate_is_404():
    r = client.post(f"/v1/approval-gates/{uuid4()}/resolve", json={"approved": True})
    assert r.status_code == 404


def test_double_resolve_is_409():
    body = _start_brainstorm()
    gid = body["pending"]["id"]
    answers = {"answers": ["a", "b", "c", "d"]}
    assert client.post(f"/v1/approval-gates/{gid}/resolve", json=answers).status_code == 200
    # The same interaction can't be resolved twice.
    assert client.post(f"/v1/approval-gates/{gid}/resolve", json=answers).status_code == 409


def test_websocket_replays_opened_interaction():
    body = _start_brainstorm()
    thread_id = body["thread_id"]
    with client.websocket_connect(f"/ws/threads/{thread_id}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        frame = ws.receive_json()
        assert frame["type"] == "interaction.opened"
        assert frame["interaction"]["id"] == body["pending"]["id"]
