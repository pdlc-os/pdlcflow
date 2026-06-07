"""Conversation history — durable transcript + list/open threads (replay)."""

from __future__ import annotations

import uuid

from app.persistence.transcript import get_transcript_store, reset_transcript_store
from fastapi.testclient import TestClient


def test_transcript_store_isolates_by_org():
    reset_transcript_store()
    s = get_transcript_store()
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    s.append(org_id=a, thread_id="a:1:x", project_id="1", role="user", text="hi A")
    s.append(org_id=a, thread_id="a:1:x", project_id="1", role="agent", text="[question] ...")
    s.append(org_id=b, thread_id="b:1:y", project_id="1", role="user", text="hi B")
    assert len(s.list_threads(org_id=a)) == 1
    assert s.list_threads(org_id=a)[0]["thread_id"] == "a:1:x"
    assert s.list_threads(org_id=a)[0]["label"] == "hi A"
    assert len(s.list_thread(org_id=a, thread_id="a:1:x")) == 2
    # b's thread is invisible to a
    assert s.list_thread(org_id=a, thread_id="b:1:y") == []
    reset_transcript_store()


def test_command_records_transcript_then_list_and_open():
    reset_transcript_store()
    from app.main import app

    c = TestClient(app)
    org, proj = str(uuid.uuid4()), str(uuid.uuid4())
    r = c.post("/v1/commands", json={"command": "doctor", "org_id": org, "project_id": proj})
    assert r.status_code == 200
    tid = r.json()["thread_id"]

    threads = c.get(f"/v1/admin/threads?org_id={org}").json()["threads"]
    assert any(t["thread_id"] == tid and "doctor" in t["label"] for t in threads)

    body = c.get(f"/v1/admin/threads/{tid}?org_id={org}").json()
    roles = [e["role"] for e in body["transcript"]]
    assert "user" in roles and "agent" in roles  # verbatim turns recorded
    reset_transcript_store()


def test_threads_admin_guarded():
    from app.main import app

    assert TestClient(app).get("/v1/admin/threads").status_code == 403  # no org → denied
