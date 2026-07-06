"""Cost analytics (PRD-07) — hermetic half.

Pricing resolution order, the catalog data file, the pure budget-threshold
decision, the effective price sheet, and DB-free route validation. Override
CRUD, budget lifecycle, and alert dedupe live in the integration suite.
"""

from __future__ import annotations

import uuid

import pytest
from app.clickstream.budget import thresholds_crossed
from app.llm.pricing import catalog_prices, catalog_version, estimate_usd
from app.main import app
from app.routes.admin.pricing import effective_sheet
from fastapi.testclient import TestClient

client = TestClient(app)
ORG = str(uuid.uuid4())
USAGE = {"input": 1_000_000, "output": 1_000_000}


# ----- catalog data file --------------------------------------------------------


def test_catalog_loads_and_matches_known_prices():
    assert catalog_version()
    prices = catalog_prices()
    assert prices["anthropic/claude-opus-4-8"] == {"in": 15.0, "out": 75.0}
    assert prices["openai/gpt-5.4-mini"] == {"in": 0.75, "out": 4.5}
    assert prices["ollama/*"] == {"in": 0.0, "out": 0.0}
    for key, p in prices.items():
        assert "/" in key and p["in"] >= 0 and p["out"] >= 0


# ----- resolution order -----------------------------------------------------------


def test_resolution_order_override_beats_catalog():
    # catalog says 2.5/15.0; the org negotiated a discount
    ov = {"openai/gpt-5.4": {"in": 1.0, "out": 5.0}}
    assert estimate_usd("openai", "gpt-5.4", USAGE, overrides=ov) == pytest.approx(6.0)
    assert estimate_usd("openai", "gpt-5.4", USAGE) == pytest.approx(17.5)


def test_resolution_order_override_prices_unknown_model():
    ov = {"openai_compatible/my-finetune": {"in": 0.5, "out": 1.5}}
    assert estimate_usd("openai_compatible", "my-finetune", USAGE, overrides=ov) == \
        pytest.approx(2.0)
    assert estimate_usd("openai_compatible", "my-finetune", USAGE) is None  # unpriced


def test_resolution_order_wildcard_and_none():
    assert estimate_usd("ollama", "anything-local", USAGE) == 0.0  # wildcard
    assert estimate_usd("openai", "gpt-99-unknown", USAGE) is None
    # malformed override never breaks the completion path
    assert estimate_usd("openai", "gpt-5.4", USAGE,
                        overrides={"openai/gpt-5.4": {"bad": "shape"}}) is None


# ----- effective sheet (provenance) -----------------------------------------------


def test_effective_sheet_provenance():
    sheet = effective_sheet({"openai/gpt-5.4": {"in": 1.0, "out": 5.0}})
    assert sheet["openai/gpt-5.4"] == {"in": 1.0, "out": 5.0, "source": "override"}
    assert sheet["anthropic/claude-opus-4-8"]["source"] == "catalog"
    # preset pricing hints appear with their own provenance
    assert sheet["openai_compatible/deepseek-chat"]["source"] == "preset"


# ----- budget threshold decision ---------------------------------------------------


def test_thresholds_crossed():
    pcts = [50, 80, 100]
    assert thresholds_crossed(0, 500, pcts, []) == []
    assert thresholds_crossed(250, 500, pcts, []) == [50]
    assert thresholds_crossed(412, 500, pcts, [50]) == [80]
    assert thresholds_crossed(600, 500, pcts, []) == [50, 80, 100]
    assert thresholds_crossed(600, 500, pcts, [50, 80, 100]) == []  # all fired
    assert thresholds_crossed(600, 0, pcts, []) == []               # no limit


# ----- DB-free route validation ----------------------------------------------------


def test_put_overrides_shape_validation():
    bad = [
        {"no-slash": {"in": 1.0, "out": 2.0}},
        {"openai/gpt-5.4": {"in": -1.0, "out": 2.0}},
        {"openai/gpt-5.4": {"input": 1.0, "output": 2.0}},
        {"openai/gpt-5.4": [1.0, 2.0]},
    ]
    for body in bad:
        r = client.put(f"/v1/admin/pricing/overrides?org_id={ORG}", json=body)
        assert r.status_code == 422, body


def test_put_budget_validation():
    r = client.put(f"/v1/admin/budget?org_id={ORG}",
                   json={"monthly_limit_usd": -5})
    assert r.status_code == 422
    r = client.put(f"/v1/admin/budget?org_id={ORG}",
                   json={"monthly_limit_usd": 500, "alert_pcts": [0]})
    assert r.status_code == 422
