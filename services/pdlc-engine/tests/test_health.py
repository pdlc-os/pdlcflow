from app.main import app
from app.routes import health
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "phase": "A"}


def test_ready_unconfigured_is_ready():
    """Hermetic default: no Postgres/Redis configured → both 'unconfigured',
    endpoint reports ready (they aren't dependencies here)."""
    health.reset_health_checkers()
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["db"] == "unconfigured"
    assert body["checks"]["redis"] == "unconfigured"
    assert body["checks"]["llm"] == "unprobed"


def test_ready_reports_dependency_status():
    """Injected checkers drive the real status/readiness logic."""
    health.reset_health_checkers()
    health.reset_health_cache()
    health.set_health_checkers(db=lambda: "ok", redis=lambda: "ok")
    try:
        r = client.get("/health/ready")
        assert r.status_code == 200 and r.json()["checks"]["db"] == "ok"

        # A degraded DB flips readiness to 503 (traffic must not route to a pod
        # that can't reach Postgres).
        health.reset_health_cache()
        health.set_health_checkers(db=lambda: "degraded")
        r = client.get("/health/ready")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"

        # A degraded Redis does NOT flip readiness (fail-open philosophy).
        health.reset_health_cache()
        health.set_health_checkers(db=lambda: "ok", redis=lambda: "degraded")
        r = client.get("/health/ready")
        assert r.status_code == 200 and r.json()["checks"]["redis"] == "degraded"
    finally:
        health.reset_health_checkers()


def test_models_org_default_is_admin_guarded():
    # The Models settings route is now DB-backed + tenant-scoped; with auth off it
    # requires an org_id (the cross-org ban) rather than returning a stub.
    r = client.get("/v1/admin/models/org-default")
    assert r.status_code == 403  # no org context → denied


def test_agents_heatmap_lists_10_personas():
    r = client.get("/v1/admin/agents/heatmap")
    assert r.status_code == 200
    assert len(r.json()["personas"]) == 10
