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


def test_models_org_default_get_returns_null_phase_a():
    r = client.get("/v1/admin/models/org-default")
    assert r.status_code == 200


def test_agents_heatmap_lists_10_personas():
    r = client.get("/v1/admin/agents/heatmap")
    assert r.status_code == 200
    assert len(r.json()["personas"]) == 10
