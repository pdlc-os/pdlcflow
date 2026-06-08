"""Continue a conversation — prior transcript is sent to the LLM, both turns recorded."""

from __future__ import annotations

import uuid

from app.main import app
from app.persistence.transcript import get_transcript_store, reset_transcript_store
from fastapi.testclient import TestClient


def test_continue_includes_history_and_records_turns():
    reset_transcript_store()
    c = TestClient(app)
    org, proj = str(uuid.uuid4()), str(uuid.uuid4())
    sess = str(uuid.uuid4())
    tid = f"{org}:{proj}:{sess}"
    # seed a prior conversation
    store = get_transcript_store()
    store.append(org_id=org, thread_id=tid, project_id=proj, role="user", text="add a dark mode toggle")
    store.append(org_id=org, thread_id=tid, project_id=proj, role="agent", text="[question] which surfaces?")

    r = c.post("/v1/commands/continue", json={"thread_id": tid, "org_id": org, "prompt": "also persist the choice"})
    assert r.status_code == 200, r.text
    assert r.json()["thread_id"] == tid and isinstance(r.json()["response"], str)

    # both new turns appended after the seeded two
    entries = store.list_thread(org_id=org, thread_id=tid)
    assert len(entries) == 4
    assert entries[2]["role"] == "user" and entries[2]["text"] == "also persist the choice"
    assert entries[3]["role"] == "agent"
    reset_transcript_store()


def test_continue_rejects_cross_org_thread():
    c = TestClient(app)
    other = str(uuid.uuid4())
    tid = f"{uuid.uuid4()}:{uuid.uuid4()}:{uuid.uuid4()}"  # belongs to a different org
    r = c.post("/v1/commands/continue", json={"thread_id": tid, "org_id": other, "prompt": "hi"})
    assert r.status_code == 403
