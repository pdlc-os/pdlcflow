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


def test_org_members_rls_locked_but_login_works_via_definer():
    """org_members is RLS-FORCEd: the non-owner role can't read another org's
    membership directly, yet login still works through the SECURITY DEFINER
    `auth_lookup` function (which runs before any org context exists)."""
    import uuid as _uuid

    from app.db.session import _sync_url
    from sqlalchemy import create_engine, text

    owner_url = _sync_url(settings.db_url)
    owner = create_engine(owner_url, future=True)
    sfx = _uuid.uuid4().hex[:8]
    org_a, org_b = _uuid.uuid4(), _uuid.uuid4()
    user_a, user_b = _uuid.uuid4(), _uuid.uuid4()

    # As the superuser owner (bypasses RLS): ensure the app role + grants, then
    # seed two orgs each with one admin user.
    with owner.begin() as c:
        c.execute(text(
            "do $$ begin if not exists (select from pg_roles where rolname='pdlc_app') "
            "then create role pdlc_app login password 'pdlc_app' nosuperuser; end if; end $$;"
        ))
        c.execute(text("grant usage on schema public to pdlc_app"))
        c.execute(text("grant select, insert on all tables in schema public to pdlc_app"))
        c.execute(text("grant execute on function auth_lookup(text) to pdlc_app"))
        c.execute(text(
            "insert into organizations (id,name,slug,settings,created_at) "
            "values (:a,'A',:sa,'{}'::jsonb,now()), (:b,'B',:sb,'{}'::jsonb,now())"
        ), {"a": org_a, "b": org_b, "sa": f"a-{sfx}", "sb": f"b-{sfx}"})
        c.execute(text("insert into users (id,email,created_at) values (:a,:ea,now()),(:b,:eb,now())"),
                  {"a": user_a, "b": user_b, "ea": f"alice-{sfx}@x.io", "eb": f"bob-{sfx}@x.io"})
        c.execute(text("insert into org_members (org_id,user_id,role) values (:oa,:ua,'admin'),(:ob,:ub,'admin')"),
                  {"oa": org_a, "ua": user_a, "ob": org_b, "ub": user_b})

    app_url = owner_url.split("://", 1)[1].split("@", 1)[1]
    app_engine = create_engine(f"postgresql+psycopg://pdlc_app:pdlc_app@{app_url}", future=True)

    # Login: auth_lookup resolves alice's org with NO org context (definer bypass).
    with app_engine.begin() as c:
        row = c.execute(text("select org_id from auth_lookup(:e)"), {"e": f"alice-{sfx}@x.io"}).first()
    assert row is not None and str(row.org_id) == str(org_a)

    # Direct read: scoped to org A sees only A's member; org B is invisible.
    with app_engine.begin() as c:
        c.execute(text("select set_config('app.org_id', :v, true)"), {"v": str(org_a)})
        n_a = c.execute(text("select count(*) from org_members")).scalar()
        sees_b = c.execute(text("select count(*) from org_members where org_id=:b"), {"b": str(org_b)}).scalar()
    assert n_a == 1 and sees_b == 0

    # With no org context, the app role sees no membership at all.
    with app_engine.begin() as c:
        assert c.execute(text("select count(*) from org_members")).scalar() == 0


def test_postgres_user_store_create_and_login_roundtrip():
    """The real PostgresUserStore: create_org + create_user (org_members under
    RLS) + get_by_email through auth_lookup."""
    from app.auth.passwords import hash_password, verify_password
    from app.auth.store import PostgresUserStore

    store = PostgresUserStore(settings)
    email = f"user-{uuid.uuid4().hex[:8]}@example.test"
    org_id = store.create_org("roundtrip-org")
    store.create_user(org_id=org_id, email=email, pw_hash=hash_password("pw-123456"), role="admin")

    rec = store.get_by_email(email)
    assert rec is not None
    assert rec["org_id"] == org_id and rec["role"] == "admin"
    assert verify_password("pw-123456", rec["pw_hash"])
    assert store.get_by_email("nobody@example.test") is None


def test_s3_artifact_roundtrip_against_minio():
    from app.persistence.artifacts import S3ArtifactStore

    store = S3ArtifactStore(settings.s3_artifacts_bucket, endpoint_url=settings.s3_endpoint_url)
    uri = store.put(str(uuid.uuid4()), str(uuid.uuid4()), "docs/PRD.md", "# integration")
    assert uri.startswith("s3://")
    assert store.get(uri) == "# integration"


def test_llm_overrides_resolve_from_db():
    """Per-tenant (org_llm_config) + per-agent (agent_llm_config) overrides are
    read back by the factory — so model selection actually honors them."""
    import json

    from app.db.rls import set_org_context
    from app.db.session import get_sync_engine
    from app.llm.factory import LLMProviderFactory
    from sqlalchemy import text

    org, _ = _seed_project()
    eng = get_sync_engine(settings)
    with eng.begin() as c:
        set_org_context(c, org)
        c.execute(
            text("insert into org_llm_config (org_id, provider, tier_map) "
                 "values (:o, 'openai', cast(:t as jsonb))"),
            {"o": org, "t": json.dumps(
                {"premium": "gpt-5.5", "balanced": "gpt-5.4", "economy": "gpt-5.4-mini"})},
        )
        c.execute(
            text("insert into agent_llm_config (org_id, agent_persona, provider, model_id) "
                 "values (:o, 'neo', 'anthropic', 'claude-opus-4-8')"),
            {"o": org},
        )

    f = LLMProviderFactory(db=eng)
    org_cfg = f._org_default(org)
    assert org_cfg.provider == "openai"
    assert org_cfg.tier_map_override["premium"] == "gpt-5.5"

    agent_cfg = f._agent_override(org, "neo")
    assert agent_cfg.provider == "anthropic"
    assert agent_cfg.model_id_override == "claude-opus-4-8"

    # No row / non-uuid org → no override (falls through to instance default).
    assert f._agent_override(org, "muse") is None
    assert f._org_default(str(uuid.uuid4())) is None
    assert f._org_default("self-host") is None


def test_admin_models_route_persists_and_reads():
    from app.main import app
    from fastapi.testclient import TestClient

    org, _ = _seed_project()
    c = TestClient(app)

    r = c.put(f"/v1/admin/models/org-default?org_id={org}", json={
        "provider": "gemini",
        "tier_map": {"premium": "gemini-3.1-pro", "balanced": "gemini-3.5-flash",
                     "economy": "gemini-3.1-flash-lite"}})
    assert r.status_code == 200
    assert c.get(f"/v1/admin/models/org-default?org_id={org}").json()["provider"] == "gemini"

    r2 = c.put(f"/v1/admin/models/agent-overrides/neo?org_id={org}", json={
        "agent_persona": "neo", "provider": "openai", "model_id": "gpt-5.5"})
    assert r2.status_code == 200
    rows = c.get(f"/v1/admin/models/agent-overrides?org_id={org}").json()
    assert any(a["agent_persona"] == "neo" and a["model_id"] == "gpt-5.5" for a in rows)


def test_postgres_work_summary_splits_actors():
    """work_summary over real events: human (gate.resolved) vs agent (agent.invoked)
    vs system (deploy.succeeded), aggregated for the org."""
    from app.analytics.postgres_store import PostgresAnalyticsStore
    from app.clickstream.sinks.postgres import PostgresSink
    from event_schema import EventEnvelope

    org = uuid.uuid4()
    proj = uuid.uuid4()
    PostgresSink(settings.db_url).write([
        EventEnvelope(event_type="gate.resolved", org_id=org, project_id=proj, actor="dev@acme",
                      payload={"gate_id": "g1"}),
        EventEnvelope(event_type="agent.invoked", org_id=org, project_id=proj,
                      payload={"agent_persona": "neo", "tokens_in": 7, "tokens_out": 3}),
        EventEnvelope(event_type="deploy.succeeded", org_id=org, project_id=proj, payload={}),
    ])
    s = PostgresAnalyticsStore(settings).work_summary(org_id=str(org))
    assert s["by_actor_type"]["human"] >= 1
    assert s["by_actor_type"]["agent"] >= 1
    assert s["by_actor_type"]["system"] >= 1
    assert s["by_agent"]["neo"]["tokens"] >= 10


def test_checkpoint_tables_are_rls_forced():
    """build_checkpointer applies FORCE RLS to the LangGraph checkpoint tables so
    threads isolate per org (thread_id prefix = app.org_id). Cross-org isolation
    as the non-owner role is verified on docker; here (CI superuser) we assert the
    RLS machinery is wired."""
    from types import SimpleNamespace

    from app.db.session import get_sync_engine
    from app.runtime.graph_runner import build_checkpointer
    from sqlalchemy import text

    cfg = SimpleNamespace(use_postgres_checkpointer=True, db_url=settings.db_url, pg_pool_max_size=5)
    ck = build_checkpointer(cfg)
    assert type(ck).__name__ == "PostgresSaver"  # not a MemorySaver fallback

    with get_sync_engine(settings).begin() as c:
        rows = c.execute(text(
            "select relname, relrowsecurity, relforcerowsecurity from pg_class "
            "where relname in ('checkpoints','checkpoint_writes','checkpoint_blobs')"
        )).all()
    assert len(rows) == 3
    for _, enabled, forced in rows:
        assert enabled and forced
