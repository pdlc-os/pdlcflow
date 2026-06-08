"""Chat attachment upload — text-like files return their content; binaries are stored."""

from __future__ import annotations

import uuid

from app.main import app
from fastapi.testclient import TestClient


def test_upload_text_returns_content():
    c = TestClient(app)
    org, proj = str(uuid.uuid4()), str(uuid.uuid4())
    r = c.post(f"/v1/uploads?org_id={org}",
               files={"file": ("notes.md", b"# Hello\nworld", "text/markdown")},
               data={"project_id": proj})
    assert r.status_code == 200
    j = r.json()
    assert j["is_text"] is True and j["filename"] == "notes.md" and "Hello" in j["text"]
    assert j["uri"]


def test_upload_binary_is_stored_without_text():
    c = TestClient(app)
    org, proj = str(uuid.uuid4()), str(uuid.uuid4())
    r = c.post(f"/v1/uploads?org_id={org}",
               files={"file": ("img.png", b"\x89PNG\x00\x01\x02\x03", "image/png")},
               data={"project_id": proj})
    assert r.status_code == 200
    j = r.json()
    assert j["is_text"] is False and j["text"] is None and j["filename"] == "img.png"
