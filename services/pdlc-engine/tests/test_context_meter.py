"""Context-window usage meter (per project)."""

from __future__ import annotations

import uuid

from app.analytics import get_analytics_store, reset_analytics_store
from event_schema import EventEnvelope
from fastapi.testclient import TestClient


def _spent(org, proj, model, tin, tout=0):
    return EventEnvelope(event_type="llm.tokens_spent", org_id=org, project_id=proj,
                         payload={"model_id": model, "tokens_in": tin, "tokens_out": tout})


def test_context_usage_tracks_peak_vs_window():
    reset_analytics_store()
    org, proj = uuid.uuid4(), uuid.uuid4()
    get_analytics_store().ingest([
        _spent(org, proj, "claude-opus-4-8", 40_000, 1_000),
        _spent(org, proj, "claude-opus-4-8", 120_000, 2_000),
    ])
    u = get_analytics_store().context_usage(org_id=str(org), project_id=str(proj))
    assert u["peak_prompt_tokens"] == 120_000
    assert u["context_window"] == 200_000  # opus window
    assert u["pct_used"] == 0.6 and u["near_limit"] is False and u["calls"] == 2
    reset_analytics_store()


def test_context_usage_near_limit_flag():
    reset_analytics_store()
    org, proj = uuid.uuid4(), uuid.uuid4()
    get_analytics_store().ingest([_spent(org, proj, "claude-haiku-4-5", 180_000)])
    u = get_analytics_store().context_usage(org_id=str(org), project_id=str(proj))
    assert u["near_limit"] is True  # 180k / 200k = 0.9
    reset_analytics_store()


def test_context_endpoint_and_admin_guard():
    reset_analytics_store()
    from app.main import app

    org, proj = uuid.uuid4(), uuid.uuid4()
    get_analytics_store().ingest([_spent(org, proj, "gpt-5.5", 10, 5)])
    c = TestClient(app)
    assert c.get("/v1/admin/context").status_code == 403  # no org → denied
    r = c.get(f"/v1/admin/context?org_id={org}&project_id={proj}")
    assert r.status_code == 200
    assert r.json()["model_id"] == "gpt-5.5" and r.json()["context_window"] == 400_000
    reset_analytics_store()
