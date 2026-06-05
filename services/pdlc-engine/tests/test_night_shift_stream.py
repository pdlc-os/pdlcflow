"""Phase H bundle 2 — live night-shift verdict streaming (hermetic, in-memory bus).

Drives a /night-shift run with the app lifespan active (so the emitter is wired
to the in-memory event bus) and asserts Sentinel verdicts + completion are
fanned out to the thread's WebSocket channel. The Redis transport is the same
interface, verified via docker-compose.
"""

from __future__ import annotations

from uuid import uuid4

from app.main import app
from app.runtime import get_event_bus
from fastapi.testclient import TestClient

ORG = str(uuid4())
PROJ = str(uuid4())

_SEED = {
    "tasks": [
        {"external_id": "bd-1", "title": "dm", "labels": ["domain:backend"], "depends_on": [], "wave": 1},
    ],
    "commits": ["feat: dark mode"],
    "deploy_candidates": ["staging"],
}


def test_night_shift_verdicts_stream_to_thread_channel():
    # Context-manager TestClient runs lifespan → wire_event_bus + wire_emitter.
    with TestClient(app) as client:
        r = client.post(
            "/v1/commands",
            json={"command": "night-shift", "org_id": ORG, "project_id": PROJ,
                  "feature": "dark mode", "seed_state": _SEED},
        )
        body = r.json()
        thread_id = body["thread_id"]
        assert body["pending"]["gate_kind"] == "night_shift_contract"

        client.post(f"/v1/approval-gates/{body['pending']['id']}/resolve", json={"approved": True})

        frames = get_event_bus().history(f"thread:{thread_id}")
        types = [f["type"] for f in frames]
        # Sentinel verdicts streamed, with real verdict values + stage labels.
        verdicts = [f for f in frames if f["type"] == "night_shift.verdict"]
        assert verdicts, f"expected verdict frames, got {types}"
        assert {v.get("stage") for v in verdicts} == {"build", "ship"}
        assert all("verdict" in v for v in verdicts)
        assert "night_shift.completed" in types

        # A WS client attaching after the run still replays the frames.
        with client.websocket_connect(f"/ws/threads/{thread_id}") as ws:
            assert ws.receive_json()["type"] == "hello"
            seen = {ws.receive_json()["type"] for _ in range(len(frames))}
            assert "night_shift.verdict" in seen
