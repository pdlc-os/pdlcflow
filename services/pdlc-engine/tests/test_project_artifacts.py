"""Project artifact listing/reading + task board routes (T3-4, T3-6).

Hermetic: the in-memory artifact + task stores back these, so a seeded store is
enough to exercise list/read/tasks end-to-end via the API.
"""

from __future__ import annotations

import uuid

import pytest
from app.main import app
from fastapi.testclient import TestClient
from pdlc_graph.ports import (
    get_task_store,
    put_artifact,
    reset_artifact_store,
    reset_current_org,
    reset_task_store,
    set_current_org,
)

client = TestClient(app)
ORG = str(uuid.uuid4())
PROJ = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _fresh():
    reset_artifact_store()
    reset_task_store()
    yield
    reset_artifact_store()
    reset_task_store()


def _seed_artifacts():
    tok = set_current_org(ORG)
    try:
        put_artifact(PROJ, "docs/PRD.md", "# PRD\nthe product")
        put_artifact(PROJ, "docs/pdlc/memory/DECISIONS.md", "# Decisions")
    finally:
        reset_current_org(tok)


def test_list_and_read_project_artifacts():
    _seed_artifacts()
    r = client.get(f"/v1/projects/{PROJ}/artifacts?org_id={ORG}")
    assert r.status_code == 200
    paths = r.json()["artifacts"]
    assert "docs/PRD.md" in paths and "docs/pdlc/memory/DECISIONS.md" in paths

    c = client.get(f"/v1/projects/{PROJ}/artifacts/content?org_id={ORG}&path=docs/PRD.md")
    assert c.status_code == 200 and "the product" in c.json()["content"]

    missing = client.get(
        f"/v1/projects/{PROJ}/artifacts/content?org_id={ORG}&path=docs/nope.md")
    assert missing.status_code == 404


def test_artifacts_are_org_scoped():
    _seed_artifacts()
    other = str(uuid.uuid4())
    r = client.get(f"/v1/projects/{PROJ}/artifacts?org_id={other}")
    assert r.json()["artifacts"] == []  # another org sees nothing under this project


def test_list_project_tasks():
    store = get_task_store()
    store.create(org_id=ORG, project_id=PROJ, title="build the thing", body="",
                 labels=["domain:api"], external_id="bd-1")
    store.create(org_id=ORG, project_id=PROJ, title="test it", body="",
                 labels=[], external_id="bd-2")
    r = client.get(f"/v1/projects/{PROJ}/tasks?org_id={ORG}")
    assert r.status_code == 200
    tasks = r.json()["tasks"]
    assert {t["external_id"] for t in tasks} == {"bd-1", "bd-2"}
    assert all(t["status"] for t in tasks)
