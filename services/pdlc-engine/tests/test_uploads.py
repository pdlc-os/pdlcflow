"""Chat attachment upload — conversation-scoped + timestamped storage; text + doc
extraction reach the agent."""

from __future__ import annotations

import io
import uuid

from app.main import app
from fastapi.testclient import TestClient


def _post(c, org, proj, conv, fname, data, ctype):
    return c.post(f"/v1/uploads?org_id={org}",
                  files={"file": (fname, data, ctype)},
                  data={"project_id": proj, "conversation_id": conv})


def test_text_upload_is_conversation_scoped_and_timestamped():
    c = TestClient(app)
    org, proj, conv = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    r = _post(c, org, proj, conv, "notes.md", b"# Hello\nworld", "text/markdown")
    assert r.status_code == 200
    j = r.json()
    assert j["is_text"] and "Hello" in j["text"]
    # stored under the conversation folder, with a timestamped, non-colliding name
    assert f"uploads/{conv}/" in j["uri"]
    assert j["stored_as"].endswith("notes.md") and j["stored_as"] != "notes.md"


def test_same_name_same_conversation_does_not_overwrite():
    c = TestClient(app)
    org, proj, conv = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    a = _post(c, org, proj, conv, "dup.txt", b"one", "text/plain").json()
    b = _post(c, org, proj, conv, "dup.txt", b"two", "text/plain").json()
    assert a["uri"] != b["uri"] and a["stored_as"] != b["stored_as"]


def test_xlsx_text_is_extracted_for_the_llm():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Region", "Revenue"])
    ws.append(["EMEA", 1234])
    buf = io.BytesIO()
    wb.save(buf)

    c = TestClient(app)
    org, proj, conv = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    r = _post(c, org, proj, conv, "sales.xlsx", buf.getvalue(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.status_code == 200
    j = r.json()
    assert j["is_text"] is False  # binary file…
    assert j["text"] and "EMEA" in j["text"] and "Revenue" in j["text"]  # …but text extracted
