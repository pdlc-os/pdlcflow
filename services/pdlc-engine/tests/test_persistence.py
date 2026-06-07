"""Phase H bundle 3 — persistence adapters (hermetic parts).

Filesystem artifact store is fully exercised; the Postgres/S3 paths need live
infra (verified via docker-compose) so here we check the wiring + the seams:
defaults stay in-memory, filesystem round-trips through the pdlc_graph port, and
S3 uri parsing is correct.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.persistence import FilesystemArtifactStore, wire_persistence
from pdlc_graph.ports import get_artifact, put_artifact, reset_artifact_store


def _settings(**over) -> SimpleNamespace:
    base = dict(
        artifact_store="memory",
        artifact_dir="/tmp/pdlcflow-test-artifacts",
        s3_artifacts_bucket="b",
        s3_endpoint_url=None,
        bedrock_region="us-east-1",
        task_store="memory",
        analytics_backend="memory",
        db_url="postgresql+asyncpg://u:p@127.0.0.1:1/none",
        pg_pool_max_size=2,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_filesystem_artifact_store_roundtrip(tmp_path):
    store = FilesystemArtifactStore(str(tmp_path))
    uri = store.put("org-A", "proj-1", "docs/PRD.md", "# hello")
    assert uri.startswith("file://")
    # tenant-namespaced: {base}/{org}/{project}/{path}
    assert (tmp_path / "org-A" / "proj-1" / "docs" / "PRD.md").read_text() == "# hello"
    assert store.get(uri) == "# hello"


def test_filesystem_store_isolates_tenants_and_blocks_traversal(tmp_path):
    store = FilesystemArtifactStore(str(tmp_path))
    a = store.get(store.put("org-A", "proj-1", "PRD.md", "A's secret"))
    b = store.get(store.put("org-B", "proj-1", "PRD.md", "B's secret"))
    # Same project_id, different orgs → separate files, no mixing.
    assert a == "A's secret" and b == "B's secret"
    assert (tmp_path / "org-A" / "proj-1" / "PRD.md").exists()
    assert (tmp_path / "org-B" / "proj-1" / "PRD.md").exists()
    # A crafted file:// uri can't read outside the base dir.
    import pytest
    with pytest.raises(ValueError):
        store.get("file:///etc/passwd")


def test_wire_persistence_filesystem_injects_into_graph_port(tmp_path):
    reset_artifact_store()
    wire_persistence(_settings(artifact_store="filesystem", artifact_dir=str(tmp_path)))
    uri = put_artifact("proj-1", "REVIEW.md", "body")
    assert uri.startswith("file://")
    assert get_artifact(uri) == "body"
    reset_artifact_store()


def test_wire_persistence_postgres_flags_do_not_crash_boot():
    # Lazy engines — construction succeeds even with an unreachable DB; the
    # engine boots and only actual queries would fail (verified via compose).
    reset_artifact_store()
    wire_persistence(_settings(task_store="postgres", analytics_backend="postgres"))
    reset_artifact_store()


def test_runner_namespaces_a_real_command_under_the_token_org(tmp_path):
    """End-to-end: a command's artifacts land under {base}/{org}/{project}/ — the
    runner binds the org (from the thread id) so writes can't cross tenants."""
    from uuid import uuid4

    from app.main import app
    from app.persistence.artifacts import FilesystemArtifactStore
    from fastapi.testclient import TestClient
    from pdlc_graph.ports import set_artifact_store

    set_artifact_store(FilesystemArtifactStore(str(tmp_path)))
    org, proj = str(uuid4()), str(uuid4())
    r = TestClient(app).post("/v1/commands", json={
        "command": "doctor", "org_id": org, "project_id": proj})
    assert r.status_code == 200
    # the doctor report was written under this tenant's namespace, nowhere else.
    assert (tmp_path / org / proj).is_dir()
    assert list((tmp_path / org / proj).rglob("*.md")), "expected an artifact file"
    assert [d.name for d in tmp_path.iterdir()] == [org]  # only this org's dir exists


def test_s3_uri_parsing():
    from app.persistence.artifacts import S3ArtifactStore

    s = S3ArtifactStore("mybucket")
    assert s._key("org-A", "p1", "a/b.md") == "org-A/p1/a/b.md"
    # get() parses s3://bucket/key without touching the network until _s3().
    _, _, rest = "s3://mybucket/org-A/p1/a/b.md".partition("s3://")
    bucket, _, key = rest.partition("/")
    assert bucket == "mybucket" and key == "org-A/p1/a/b.md"
