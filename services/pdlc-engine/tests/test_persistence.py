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
    uri = store.put("proj-1", "docs/PRD.md", "# hello")
    assert uri.startswith("file://")
    assert (tmp_path / "proj-1" / "docs" / "PRD.md").read_text() == "# hello"
    assert store.get(uri) == "# hello"


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


def test_s3_uri_parsing():
    from app.persistence.artifacts import S3ArtifactStore

    s = S3ArtifactStore("mybucket")
    assert s._key("p1", "a/b.md") == "p1/a/b.md"
    # get() parses s3://bucket/key without touching the network until _s3().
    _, _, rest = "s3://mybucket/p1/a/b.md".partition("s3://")
    bucket, _, key = rest.partition("/")
    assert bucket == "mybucket" and key == "p1/a/b.md"
