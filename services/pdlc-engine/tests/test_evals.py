"""Phase J — engine-side eval wiring + analytics surface (hermetic)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.analytics import get_analytics_store
from app.evals import wire_evals
from app.main import app
from event_schema import EventEnvelope
from fastapi.testclient import TestClient

pytestmark = pytest.mark.eval

ORG = str(uuid4())
PROJ = str(uuid4())


def test_wire_evals_toggles_harness_and_parses_blocking():
    from pdlc_graph.evals import evals_enabled
    from pdlc_graph.evals.registry import REGISTRY, is_blocking

    assert wire_evals(SimpleNamespace(run_evals=False, eval_blocking="", wire_llm=False)) is False
    assert evals_enabled() is False

    assert wire_evals(SimpleNamespace(
        run_evals=True, eval_blocking="groundedness, citation", wire_llm=False, judge_tier="premium",
    )) is True
    assert evals_enabled() is True
    # blocking overrides parsed from the comma-separated env value
    assert is_blocking(REGISTRY["groundedness"]) and is_blocking(REGISTRY["citation"])
    assert not is_blocking(REGISTRY["agent_output_quality"])


def _scored(eval_id: str, target: str, score: float, passed: bool) -> EventEnvelope:
    return EventEnvelope(
        event_type="eval.scored", org_id=ORG, project_id=PROJ,
        payload={"eval_id": eval_id, "target": target, "dimension": "quality",
                 "score": score, "passed": passed, "threshold": 0.6,
                 "blocking": False, "kind": "llm_judge", "trigger": "prd"},
    )


def test_eval_summary_aggregates_by_eval_and_agent():
    store = get_analytics_store()
    store.ingest([
        _scored("agent_output_quality", "atlas", 0.8, True),
        _scored("agent_output_quality", "atlas", 0.6, False),
        _scored("groundedness", "neo", 0.9, True),
    ])
    summary = store.eval_summary(org_id=ORG)
    aq = summary["by_eval"]["agent_output_quality"]
    assert aq["n"] == 2 and aq["avg_score"] == 0.7 and aq["pass_rate"] == 0.5
    assert summary["by_agent"]["atlas"]["n"] == 2
    assert summary["by_eval"]["groundedness"]["avg_score"] == 0.9


def test_admin_evals_summary_route_requires_org_and_returns_scores():
    get_analytics_store().ingest([_scored("groundedness", "neo", 0.95, True)])
    client = TestClient(app)
    # cross-org ban: no org_id -> 403 + admin.access.denied audit
    assert client.get("/v1/admin/evals/summary").status_code == 403
    r = client.get(f"/v1/admin/evals/summary?org_id={ORG}")
    assert r.status_code == 200
    body = r.json()
    assert "by_eval" in body and "groundedness" in body["by_eval"]
