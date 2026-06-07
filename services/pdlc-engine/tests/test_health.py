from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "phase": "A"}


def test_ready():
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_models_org_default_is_admin_guarded():
    # The Models settings route is now DB-backed + tenant-scoped; with auth off it
    # requires an org_id (the cross-org ban) rather than returning a stub.
    r = client.get("/v1/admin/models/org-default")
    assert r.status_code == 403  # no org context → denied


def test_agents_heatmap_lists_10_personas():
    r = client.get("/v1/admin/agents/heatmap")
    assert r.status_code == 200
    assert len(r.json()["personas"]) == 10
