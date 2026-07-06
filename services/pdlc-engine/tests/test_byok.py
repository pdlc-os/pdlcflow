"""BYOK — per-tenant API key resolution (hermetic half).

Covers the factory's secret resolution: TTL cache, hard-fail on dangling refs
(no silent env-key fallback — that is exactly the bug BYOK fixes), and the
tenant key reaching the provider builder. The DB round-trip (secret_ref column,
COALESCE key inheritance, admin routes) lives in test_integration.py.
"""

from __future__ import annotations

import uuid
from typing import ClassVar

import pytest
from app.config import settings
from app.llm.factory import (
    LLMProviderFactory,
    SecretResolutionError,
    TenantCtx,
    invalidate_secret_cache,
)


class _FakeSecrets:
    """In-memory stand-in for app.secretstore.Secrets (injectable via ctor)."""

    def __init__(self, mapping: dict[str, str]):
        self._m = mapping
        self.calls = 0

    def resolve(self, ref: str | None) -> str | None:
        self.calls += 1
        return self._m.get(ref)


class _ExplodingSecrets:
    def resolve(self, ref):  # e.g. Fernet InvalidToken, Vault connection error
        raise RuntimeError("backend down")


@pytest.fixture(autouse=True)
def _fresh_cache():
    invalidate_secret_cache()
    yield
    invalidate_secret_cache()


def test_null_ref_means_no_tenant_key():
    f = LLMProviderFactory(secrets=_FakeSecrets({}))
    assert f._resolve_secret(None) is None  # env fallback stays legitimate


def test_ref_resolves_to_plaintext():
    f = LLMProviderFactory(secrets=_FakeSecrets({"fake:k1": "sk-tenant"}))
    assert f._resolve_secret("fake:k1") == "sk-tenant"


def test_dangling_ref_raises_not_falls_back():
    f = LLMProviderFactory(secrets=_FakeSecrets({}))
    with pytest.raises(SecretResolutionError) as ei:
        f._resolve_secret("fake:gone")
    # The error must never leak the ref or key material.
    assert "fake:gone" not in str(ei.value)


def test_backend_error_raises_secret_resolution_error():
    f = LLMProviderFactory(secrets=_ExplodingSecrets())
    with pytest.raises(SecretResolutionError):
        f._resolve_secret("enc:whatever")


def test_cache_hits_within_ttl_and_invalidation(monkeypatch):
    monkeypatch.setattr(settings, "secret_cache_ttl_s", 300)
    store = _FakeSecrets({"fake:k1": "sk-1"})
    f = LLMProviderFactory(secrets=store)
    assert f._resolve_secret("fake:k1") == "sk-1"
    assert f._resolve_secret("fake:k1") == "sk-1"
    assert store.calls == 1  # second read served from cache

    invalidate_secret_cache("fake:k1")
    store._m["fake:k1"] = "sk-2"  # rotated (stable ref, e.g. vault path)
    assert f._resolve_secret("fake:k1") == "sk-2"
    assert store.calls == 2


def test_ttl_zero_disables_cache(monkeypatch):
    monkeypatch.setattr(settings, "secret_cache_ttl_s", 0)
    store = _FakeSecrets({"fake:k1": "sk-1"})
    f = LLMProviderFactory(secrets=store)
    f._resolve_secret("fake:k1")
    f._resolve_secret("fake:k1")
    assert store.calls == 2


# ----- tenant key reaches the provider builder ------------------------------


class _Res:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row

    def scalar(self):
        return None


class _FakeConn:
    """Dispatches on table name so agent/org queries return distinct rows;
    anything else (set_org_context's set_config) returns an empty result."""

    def __init__(self, agent_row, org_row):
        self._agent_row, self._org_row = agent_row, org_row

    def execute(self, clause, params=None):
        sql = str(clause)
        if "agent_llm_config" in sql:
            return _Res(self._agent_row)
        if "org_llm_config" in sql:
            return _Res(self._org_row)
        return _Res(None)


class _FakeEngine:
    def __init__(self, agent_row=None, org_row=None):
        self._rows = (agent_row, org_row)

    def begin(self):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield _FakeConn(*self._rows)

        return _cm()


class _FakeChat:
    last: ClassVar[dict] = {}

    def __init__(self, **kw):
        _FakeChat.last = kw


def test_org_key_flows_into_builder(monkeypatch):
    monkeypatch.setattr("langchain_anthropic.ChatAnthropic", _FakeChat)
    org_row = {"provider": "anthropic", "region": None, "endpoint": None,
               "tier_map": None, "secret_ref": "fake:org-key"}
    f = LLMProviderFactory(
        db=_FakeEngine(agent_row=None, org_row=org_row),
        secrets=_FakeSecrets({"fake:org-key": "sk-tenant-A"}),
    )
    f.get_model("neo", "premium", TenantCtx(org_id=str(uuid.uuid4())))
    assert _FakeChat.last["api_key"] == "sk-tenant-A"


def test_dangling_org_ref_fails_the_call(monkeypatch):
    monkeypatch.setattr("langchain_anthropic.ChatAnthropic", _FakeChat)
    org_row = {"provider": "anthropic", "region": None, "endpoint": None,
               "tier_map": None, "secret_ref": "fake:revoked"}
    f = LLMProviderFactory(
        db=_FakeEngine(agent_row=None, org_row=org_row),
        secrets=_FakeSecrets({}),
    )
    with pytest.raises(SecretResolutionError):
        f.get_model("neo", "premium", TenantCtx(org_id=str(uuid.uuid4())))


# ----- response models physically cannot leak key material ------------------


def test_response_models_have_no_key_fields():
    from app.routes.admin.models import AgentOverrideOut, OrgDefaultOut

    for model in (OrgDefaultOut, AgentOverrideOut):
        assert "api_key" not in model.model_fields
        assert "secret_ref" not in model.model_fields
        assert "has_key" in model.model_fields
