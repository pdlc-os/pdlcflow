"""Integration tests — exercise the REAL Postgres / Redis / MinIO adapters.

Skipped unless PDLC_RUN_INTEGRATION=1 (the integration CI job sets it after
spinning up the service containers + running `alembic upgrade head`). These are
the tests that validate what the hermetic suite structurally cannot.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from app.config import settings

pytestmark = pytest.mark.integration


def test_alembic_schema_present():
    from app.db.session import get_sync_engine
    from sqlalchemy import inspect

    names = set(inspect(get_sync_engine(settings)).get_table_names())
    assert {"events", "tasks", "approval_gates", "organizations", "projects"} <= names


def _seed_project() -> tuple[str, str]:
    """Insert a real org → squad → project so tasks satisfy their FK."""
    from app.db.models import Organization, Project, Squad
    from app.db.session import get_sync_engine
    from sqlalchemy import insert

    org_id, squad_id, proj_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with get_sync_engine(settings).begin() as c:
        c.execute(insert(Organization).values(id=org_id, name="Acme", slug=f"acme-{org_id.hex[:8]}", settings={}))
        c.execute(insert(Squad).values(id=squad_id, org_id=org_id, name="Core", slug=f"core-{squad_id.hex[:8]}"))
        c.execute(insert(Project).values(id=proj_id, org_id=org_id, squad_id=squad_id, name="App", slug=f"app-{proj_id.hex[:8]}"))
    return str(org_id), str(proj_id)


def test_postgres_task_store_external_id_and_atomic_claim():
    from app.persistence.tasks import PostgresTaskStore

    store = PostgresTaskStore(settings)
    org, proj = _seed_project()
    a = store.create(org, proj, "data model", "body", ["domain:backend"], external_id="bd-1")
    b = store.create(org, proj, "api", "body", [], external_id="bd-2")
    assert a == "bd-1" and b == "bd-2"
    store.add_dependency(org, proj, "bd-1", "bd-2")

    rows = {r["external_id"]: r for r in store.list(org, proj)}
    assert rows["bd-2"]["depends_on"] == ["bd-1"]

    # Atomic claim: first wins; same branch in the project is rejected; double-claim fails.
    assert store.claim(org, proj, "bd-1", "feat/x", "dev@acme") is True
    assert store.claim(org, proj, "bd-2", "feat/x", "dev@acme") is False  # branch taken
    assert store.claim(org, proj, "bd-1", "feat/y", "dev@acme") is False  # already claimed


def test_postgres_analytics_rollup_over_real_events():
    from app.analytics.postgres_store import PostgresAnalyticsStore
    from app.clickstream.sinks.postgres import PostgresSink
    from event_schema import EventEnvelope

    org, proj = uuid.uuid4(), uuid.uuid4()
    PostgresSink(settings.db_url).write([
        EventEnvelope(
            event_type="agent.invoked", org_id=org, project_id=proj, roadmap_id="F-int",
            payload={"agent_persona": "neo", "tokens_in": 10, "tokens_out": 5, "usd_estimate": 0.01},
        )
    ])
    store = PostgresAnalyticsStore(settings)
    rows = store.rollup(org_id=str(org), dimension="roadmap")
    hit = next(r for r in rows if r["key"] == "F-int")
    assert hit["events"] >= 1 and hit["tokens"] >= 15


def test_postgres_checkpointer_durable_across_runner_instances():
    from types import SimpleNamespace

    from app.runtime.graph_runner import GraphRunner, build_checkpointer

    cfg = SimpleNamespace(use_postgres_checkpointer=True, db_url=settings.db_url, pg_pool_max_size=5)
    org, proj = str(uuid.uuid4()), str(uuid.uuid4())
    thread_id = f"{org}:{proj}:{uuid.uuid4()}"
    state = {
        "org_id": org, "project_id": proj, "phase": "Inception",
        "interaction_mode": "socratic", "feature": "durable", "brainstorm_log": [],
    }
    pending = GraphRunner(checkpointer=build_checkpointer(cfg)).start(thread_id, state)
    assert pending is not None  # paused at the first Socratic round

    # A brand-new runner (fresh pool, same Postgres) resumes the parked thread.
    nxt = GraphRunner(checkpointer=build_checkpointer(cfg)).resume(thread_id, {"answers": ["a", "b", "c", "d"]})
    assert nxt is not None


def test_redis_bus_publish_replay_and_subscribe():
    from app.runtime.redis_bus import RedisEventBus

    bus = RedisEventBus(settings.redis_url)
    channel = f"thread:itest-{uuid.uuid4().hex}"
    bus.publish(channel, {"type": "interaction.opened", "n": 1})
    assert bus.history(channel)[-1]["n"] == 1

    async def _first():
        async for frame in bus.listen(channel):  # replays history first
            return frame

    got = asyncio.run(asyncio.wait_for(_first(), timeout=5))
    assert got["n"] == 1


def test_rls_force_blocks_cross_org_as_non_owner_role():
    """RLS FORCE: connected as a NON-superuser role, a session only ever sees its
    own org's rows even when it asks for another org's — and can't insert for one.
    """
    import uuid as _uuid

    from app.db.session import _sync_url
    from sqlalchemy import create_engine, text

    owner_url = _sync_url(settings.db_url)  # the CI job's db_url is the superuser
    owner = create_engine(owner_url, future=True)

    # 1) ensure the schema is FORCEd + a non-owner role exists with grants.
    with owner.begin() as c:
        for t in ("events",):
            c.execute(text(f"alter table {t} force row level security"))
        c.execute(text(
            "do $$ begin if not exists (select from pg_roles where rolname='pdlc_app') "
            "then create role pdlc_app login password 'pdlc_app' nosuperuser; end if; end $$;"
        ))
        c.execute(text("grant usage on schema public to pdlc_app"))
        c.execute(text("grant select, insert on all tables in schema public to pdlc_app"))

    org_a, org_b = _uuid.uuid4(), _uuid.uuid4()
    proj = _uuid.uuid4()

    # 2) as the non-owner app role, write an event for org A with app.org_id=A.
    app_url = owner_url.split("://", 1)[1].split("@", 1)[1]  # host:port/db
    app_engine = create_engine(f"postgresql+psycopg://pdlc_app:pdlc_app@{app_url}", future=True)
    insert_sql = text(
        "insert into events (event_id, event_type, schema_version, ts, org_id, project_id, domains, payload) "
        "values (gen_random_uuid(), 'agent.invoked', 1, now(), :org, :proj, '{}'::text[], '{}'::jsonb)"
    )
    with app_engine.begin() as c:
        c.execute(text("select set_config('app.org_id', :v, true)"), {"v": str(org_a)})
        c.execute(insert_sql, {"org": str(org_a), "proj": str(proj)})

    # 3) inserting for org B while app.org_id=A is rejected by the policy.
    with app_engine.begin() as c:
        c.execute(text("select set_config('app.org_id', :v, true)"), {"v": str(org_a)})
        try:
            c.execute(insert_sql, {"org": str(org_b), "proj": str(proj)})
            wrote_cross_org = True
        except Exception:
            wrote_cross_org = False
    assert wrote_cross_org is False, "RLS should reject an insert for a different org"

    # 4) a session scoped to org B sees zero of org A's events (even querying all).
    with app_engine.begin() as c:
        c.execute(text("select set_config('app.org_id', :v, true)"), {"v": str(org_b)})
        seen_b = c.execute(text("select count(*) from events")).scalar()
    with app_engine.begin() as c:
        c.execute(text("select set_config('app.org_id', :v, true)"), {"v": str(org_a)})
        seen_a = c.execute(text("select count(*) from events where org_id = :o"), {"o": str(org_a)}).scalar()
    assert seen_b == 0 and seen_a >= 1


def test_s3_artifact_roundtrip_against_minio():
    from app.persistence.artifacts import S3ArtifactStore

    store = S3ArtifactStore(settings.s3_artifacts_bucket, endpoint_url=settings.s3_endpoint_url)
    uri = store.put(str(uuid.uuid4()), "docs/PRD.md", "# integration")
    assert uri.startswith("s3://")
    assert store.get(uri) == "# integration"
