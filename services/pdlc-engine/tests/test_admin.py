"""Atlas Console admin route tests — drive each rollup/timeline/export route via
TestClient against an in-memory analytics store seeded with EventEnvelopes."""

from __future__ import annotations

import csv
import io
from uuid import UUID, uuid4

import app.analytics as analytics
import pytest
from app.main import app
from event_schema import EventEnvelope
from fastapi.testclient import TestClient

client = TestClient(app)

ORG = UUID("00000000-0000-0000-0000-0000000000aa")
OTHER_ORG = UUID("00000000-0000-0000-0000-0000000000bb")
PROJ = UUID("00000000-0000-0000-0000-0000000000cc")
INIT_A = UUID("00000000-0000-0000-0000-00000000a001")
INIT_B = UUID("00000000-0000-0000-0000-00000000a002")
SQUAD_A = UUID("00000000-0000-0000-0000-00000000b001")


def _ev(
    *,
    event_type: str = "agent.invoked",
    org_id: UUID = ORG,
    initiative_id: UUID | None = None,
    squad_id: UUID | None = None,
    domains: list[str] | None = None,
    roadmap_id: str | None = None,
    agent_persona: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    usd: float = 0.0,
) -> EventEnvelope:
    payload: dict = {}
    if agent_persona is not None:
        payload["agent_persona"] = agent_persona
    if tokens_in or tokens_out:
        payload["tokens_in"] = tokens_in
        payload["tokens_out"] = tokens_out
    if usd:
        payload["usd_estimate"] = usd
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        org_id=org_id,
        project_id=PROJ,
        initiative_id=initiative_id,
        squad_id=squad_id,
        domains=domains or [],
        roadmap_id=roadmap_id,
        payload=payload,
    )


@pytest.fixture(autouse=True)
def _fresh_store():
    analytics.reset_analytics_store()
    yield
    analytics.reset_analytics_store()


def _seed() -> None:
    store = analytics.get_analytics_store()
    store.ingest(
        [
            _ev(
                initiative_id=INIT_A,
                squad_id=SQUAD_A,
                domains=["payments", "security"],
                roadmap_id="F-001",
                agent_persona="atlas",
                tokens_in=100,
                tokens_out=50,
                usd=1.5,
            ),
            _ev(
                event_type="agent.responded",
                initiative_id=INIT_A,
                squad_id=SQUAD_A,
                domains=["payments"],
                roadmap_id="F-001",
                agent_persona="atlas",
                tokens_in=10,
                tokens_out=5,
                usd=0.25,
            ),
            _ev(
                initiative_id=INIT_B,
                squad_id=SQUAD_A,
                domains=["security"],
                roadmap_id="F-002",
                agent_persona="bolt",
                tokens_in=20,
                tokens_out=20,
                usd=0.5,
            ),
            # Another org's event — must never leak into ORG's rollups.
            _ev(
                org_id=OTHER_ORG,
                initiative_id=INIT_A,
                roadmap_id="F-001",
                agent_persona="atlas",
                tokens_in=999,
                tokens_out=999,
                usd=99.0,
            ),
        ]
    )


def test_live_returns_events_most_recent_first():
    _seed()
    r = client.get("/v1/admin/live", params={"org_id": str(ORG)})
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) == 3  # other org excluded
    # most-recent first → last seeded ORG event (bolt / F-002) leads
    assert events[0]["roadmap_id"] == "F-002"


def test_live_respects_limit():
    _seed()
    r = client.get("/v1/admin/live", params={"org_id": str(ORG), "limit": 1})
    assert r.status_code == 200
    assert len(r.json()["events"]) == 1


def test_initiatives_rollup():
    _seed()
    r = client.get("/v1/admin/initiatives/rollup", params={"org_id": str(ORG)})
    assert r.status_code == 200
    rows = {row["key"]: row for row in r.json()["rows"]}
    assert set(rows) == {str(INIT_A), str(INIT_B)}
    assert rows[str(INIT_A)]["events"] == 2
    assert rows[str(INIT_A)]["tokens"] == 165  # 150 + 15
    assert rows[str(INIT_A)]["usd"] == 1.75
    assert rows[str(INIT_B)]["events"] == 1


def test_initiatives_rollup_date_filter_excludes_all():
    _seed()
    r = client.get(
        "/v1/admin/initiatives/rollup",
        params={"org_id": str(ORG), "from": "2999-01-01T00:00:00+00:00"},
    )
    assert r.status_code == 200
    assert r.json()["rows"] == []


def test_domains_rollup_explodes_list():
    _seed()
    r = client.get("/v1/admin/domains/rollup", params={"org_id": str(ORG)})
    assert r.status_code == 200
    rows = {row["key"]: row for row in r.json()["rows"]}
    assert set(rows) == {"payments", "security"}
    assert rows["payments"]["events"] == 2  # F-001 x2
    assert rows["security"]["events"] == 2  # F-001 + F-002


def test_squads_scoreboard():
    _seed()
    r = client.get("/v1/admin/squads/scoreboard", params={"org_id": str(ORG)})
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["key"] == str(SQUAD_A)
    assert rows[0]["events"] == 3


def test_agents_heatmap_with_org_has_cells():
    _seed()
    r = client.get("/v1/admin/agents/heatmap", params={"org_id": str(ORG)})
    assert r.status_code == 200
    body = r.json()
    assert body["personas"] == [
        "atlas", "bolt", "echo", "friday", "jarvis",
        "muse", "neo", "phantom", "pulse", "sentinel",
    ]
    cells = {c["key"]: c for c in body["cells"]}
    assert set(cells) == {"atlas", "bolt"}
    assert cells["atlas"]["events"] == 2


def test_agents_heatmap_without_org_lists_10_personas_empty_cells():
    _seed()
    r = client.get("/v1/admin/agents/heatmap")
    assert r.status_code == 200
    body = r.json()
    assert len(body["personas"]) == 10
    assert body["cells"] == []


def test_features_timeline_chronological():
    _seed()
    r = client.get(
        "/v1/admin/features/F-001/timeline", params={"org_id": str(ORG)}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["roadmap_id"] == "F-001"
    assert len(body["events"]) == 2  # only ORG's F-001 events
    types = [e["event_type"] for e in body["events"]]
    assert types == ["agent.invoked", "agent.responded"]


def test_exports_rollup_csv():
    _seed()
    r = client.get(
        "/v1/admin/exports/rollup.csv",
        params={"org_id": str(ORG), "dimension": "initiative"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    reader = list(csv.reader(io.StringIO(r.text)))
    assert reader[0] == ["key", "events", "tokens", "usd"]
    by_key = {row[0]: row for row in reader[1:]}
    assert set(by_key) == {str(INIT_A), str(INIT_B)}
    assert by_key[str(INIT_A)][1] == "2"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/admin/live",
        "/v1/admin/initiatives/rollup",
        "/v1/admin/domains/rollup",
        "/v1/admin/squads/scoreboard",
        "/v1/admin/features/F-001/timeline",
        "/v1/admin/exports/rollup.csv?dimension=initiative",
    ],
)
def test_data_route_without_org_id_is_403(path):
    # Cross-org ban: missing org_id -> 403 + an admin.access.denied audit event.
    r = client.get(path)
    assert r.status_code == 403
