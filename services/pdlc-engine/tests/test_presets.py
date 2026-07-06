"""Preset catalog + openai_compatible provider (hermetic half).

Catalog schema/drift validation, the generic builder, ModelResolutionError
semantics, the three-way registration agreement, preset routes that don't
touch the DB, config-write-time validation, and catalog-hinted pricing.
The apply-upsert round-trip lives in the integration suite.
"""

from __future__ import annotations

import uuid
from typing import ClassVar

import pytest
from app.llm.factory import _BUILDERS, ProviderConfig
from app.llm.factory import Provider as FactoryProvider
from app.llm.presets import load_catalog
from app.llm.pricing import estimate_usd
from app.llm.providers import openai_compatible as oc
from app.llm.tier_map import DEFAULT_TIER_MAP, ModelResolutionError, resolve_model_id
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
ORG = str(uuid.uuid4())

FIRST_PARTY = ("bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama")


# ----- catalog data ----------------------------------------------------------


def test_catalog_loads_and_validates():
    c = load_catalog()
    assert c.catalog_version and len(c.presets) >= 10
    for p in c.presets:
        assert set(p.tier_map) == {"premium", "balanced", "economy"}
        assert all(p.tier_map.values())
        if p.provider == "openai_compatible":
            assert p.endpoint, f"{p.id}: gateway preset must carry an endpoint"


def test_first_party_presets_mirror_default_tier_map():
    c = load_catalog()
    for provider in FIRST_PARTY:
        matches = [p for p in c.presets if p.provider == provider]
        assert matches, f"no preset for first-party provider {provider}"
        for p in matches:
            assert p.tier_map == DEFAULT_TIER_MAP[provider], f"{p.id} drifted"


def test_catalog_search_and_get():
    c = load_catalog()
    assert c.get("openrouter") is not None
    assert c.get("nope") is None
    hits = {p.id for p in c.search("deepseek")}
    assert "deepseek" in hits
    assert {p.id for p in c.search(None)} == {p.id for p in c.presets}
    # tags are searchable
    assert all("openai-compatible" in p.tags or "deepseek" in p.id.lower()
               or "deepseek" in p.label.lower()
               for p in c.search("openai-compatible"))


# ----- openai_compatible builder --------------------------------------------


class _FakeChat:
    last: ClassVar[dict] = {}

    def __init__(self, **kw):
        _FakeChat.last = kw


def test_builder_kwargs(monkeypatch):
    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChat)
    oc.build(ProviderConfig(provider="openai_compatible",
                            endpoint="https://openrouter.ai/api/v1",
                            secret_value="sk-or-x"), "deepseek/deepseek-chat")
    assert _FakeChat.last == {"model": "deepseek/deepseek-chat",
                              "base_url": "https://openrouter.ai/api/v1",
                              "api_key": "sk-or-x"}
    # keyless local server → placeholder key, never empty
    oc.build(ProviderConfig(provider="openai_compatible",
                            endpoint="http://localhost:8000/v1"), "local-model")
    assert _FakeChat.last["api_key"] == "not-needed"


def test_builder_requires_endpoint():
    with pytest.raises(ValueError, match="endpoint"):
        oc.build(ProviderConfig(provider="openai_compatible"), "m")


# ----- tier resolution safety -----------------------------------------------


def test_resolve_model_id_raises_model_resolution_error():
    with pytest.raises(ModelResolutionError):
        resolve_model_id("openai_compatible", "premium")  # no built-in map
    with pytest.raises(ModelResolutionError):
        resolve_model_id("openai_compatible", "premium", {"balanced": "x"})  # partial
    assert resolve_model_id("openai_compatible", "premium",
                            {"premium": "glm-4.6", "balanced": "x", "economy": "y"}) == "glm-4.6"


# ----- registration agreement (the three points move in lockstep) ------------


def test_provider_registration_agreement():
    from app.db.models import AgentLLMConfig, OrgLLMConfig
    from app.routes.admin.models import Provider as RouteProvider

    factory_providers = set(FactoryProvider.__args__)
    route_providers = set(RouteProvider.__args__)

    assert set(_BUILDERS) == factory_providers
    # route = factory minus the CLI providers (single-user self-host only)
    assert route_providers == factory_providers - {"claude_code", "codex", "gemini_cli"}
    # every preset uses a route-selectable provider
    assert {p.provider for p in load_catalog().presets} <= route_providers
    # DB CHECK constraints include exactly the route providers
    for table in (OrgLLMConfig.__table__, AgentLLMConfig.__table__):
        ck = next(c for c in table.constraints
                  if getattr(c, "name", "") and "provider" in str(getattr(c, "name", "")))
        assert "openai_compatible" in str(ck.sqltext)
        for p in route_providers:
            assert f"'{p}'" in str(ck.sqltext)


# ----- routes (no DB on these paths) -----------------------------------------


def test_presets_route_lists_and_searches():
    r = client.get(f"/v1/admin/models/presets?org_id={ORG}")
    assert r.status_code == 200
    body = r.json()
    assert body["catalog_version"]
    ids = {p["id"] for p in body["presets"]}
    assert {"openrouter", "deepseek", "bedrock-us"} <= ids
    assert all("pricing_hints" not in p for p in body["presets"])
    openrouter = next(p for p in body["presets"] if p["id"] == "openrouter")
    assert openrouter["needs_secret"] is True
    bedrock = next(p for p in body["presets"] if p["id"] == "bedrock-us")
    assert bedrock["needs_secret"] is False

    filtered = client.get(f"/v1/admin/models/presets?org_id={ORG}&q=kimi").json()
    assert {p["id"] for p in filtered["presets"]} == {"moonshot-kimi"}


def test_apply_unknown_preset_404():
    assert client.post(
        f"/v1/admin/models/presets/nope/apply?org_id={ORG}").status_code == 404


def test_put_openai_compatible_requires_endpoint_and_tier_map():
    tiers = {"premium": "a", "balanced": "b", "economy": "c"}
    # missing endpoint
    r = client.put(f"/v1/admin/models/org-default?org_id={ORG}", json={
        "provider": "openai_compatible", "tier_map": tiers})
    assert r.status_code == 422
    # incomplete tier map
    r = client.put(f"/v1/admin/models/org-default?org_id={ORG}", json={
        "provider": "openai_compatible", "endpoint": "https://8.8.8.8/v1",
        "tier_map": {"premium": "a"}})
    assert r.status_code == 422
    # SSRF: private endpoint rejected at write time
    r = client.put(f"/v1/admin/models/org-default?org_id={ORG}", json={
        "provider": "openai_compatible", "endpoint": "http://169.254.169.254/v1",
        "tier_map": tiers})
    assert r.status_code == 422
    # agent override: same endpoint guard
    r = client.put(f"/v1/admin/models/agent-overrides/neo?org_id={ORG}", json={
        "agent_persona": "neo", "provider": "openai_compatible", "model_id": "m"})
    assert r.status_code == 422


# ----- pricing hints ----------------------------------------------------------


def test_estimate_usd_uses_catalog_hints():
    usage = {"input": 1_000_000, "output": 1_000_000}
    # deepseek-chat hint: 0.27 in + 1.10 out
    assert estimate_usd("openai_compatible", "deepseek-chat", usage) == pytest.approx(1.37)
    # unknown gateway model → UNPRICED (None, not $0 — PRD-07 FR-5)
    assert estimate_usd("openai_compatible", "totally-unknown", usage) is None
    # pricing catalog still wins for first-party
    assert estimate_usd("anthropic", "claude-opus-4-8", usage) == pytest.approx(90.0)
