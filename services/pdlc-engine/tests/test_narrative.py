"""Work narrative + actor attribution (hermetic).

Verifies the clickstream splits human vs agent vs system work, the analytics
`work_summary` aggregates it over a window, and the /admin/narrative endpoint
returns stats + an LLM narrative (deterministic stub when the LLM is unwired).
"""

from __future__ import annotations

import uuid

from app.analytics import get_analytics_store, reset_analytics_store
from event_schema import EventEnvelope, actor_type_for
from fastapi.testclient import TestClient


def test_actor_type_classifier():
    assert actor_type_for("gate.resolved") == "human"
    assert actor_type_for("decision.recorded") == "human"
    assert actor_type_for("agent.invoked") == "agent"
    assert actor_type_for("step.completed") == "agent"
    assert actor_type_for("error") == "system"
    assert actor_type_for("deploy.succeeded") == "system"


def _seed(org: str, proj: str) -> None:
    store = get_analytics_store()
    o, p = uuid.UUID(org), uuid.UUID(proj)
    store.ingest([
        EventEnvelope(event_type="gate.resolved", org_id=o, project_id=p, actor="dev@acme",
                      payload={"gate_id": "g1"}),
        EventEnvelope(event_type="decision.recorded", org_id=o, project_id=p, actor="dev@acme",
                      payload={}),
        EventEnvelope(event_type="agent.invoked", org_id=o, project_id=p,
                      payload={"agent_persona": "neo", "tokens_in": 10, "tokens_out": 5}),
        EventEnvelope(event_type="step.completed", org_id=o, project_id=p,
                      payload={"agent_persona": "bolt"}),
        EventEnvelope(event_type="deploy.succeeded", org_id=o, project_id=p, payload={}),
    ])


def test_work_summary_splits_human_agent_system():
    reset_analytics_store()
    org, proj = str(uuid.uuid4()), str(uuid.uuid4())
    _seed(org, proj)
    s = get_analytics_store().work_summary(org_id=org)
    assert s["total_events"] == 5
    assert s["by_actor_type"] == {"human": 2, "agent": 2, "system": 1}
    assert s["by_agent"]["neo"]["events"] == 1 and s["by_agent"]["neo"]["tokens"] == 15
    assert s["by_agent"]["bolt"]["events"] == 1
    # milestones surfaced for the narrative
    kinds = {n["event_type"] for n in s["notable"]}
    assert {"gate.resolved", "decision.recorded", "deploy.succeeded"} <= kinds
    reset_analytics_store()


def test_narrative_endpoint_returns_stats_and_text():
    reset_analytics_store()
    from app.main import app

    org, proj = str(uuid.uuid4()), str(uuid.uuid4())
    _seed(org, proj)
    c = TestClient(app)
    r = c.get(f"/v1/admin/narrative?org_id={org}")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["by_actor_type"]["human"] == 2
    assert isinstance(body["narrative"], str) and body["narrative"]  # stub or real text
    reset_analytics_store()


def test_narrative_endpoint_is_admin_guarded():
    from app.main import app

    r = TestClient(app).get("/v1/admin/narrative")
    assert r.status_code == 403  # no org context → denied
