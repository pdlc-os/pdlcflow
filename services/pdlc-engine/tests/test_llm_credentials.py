"""Direct-API providers take the configured `secret_value` when set, and
otherwise OMIT the key kwarg so the SDK reads its own env credential — instead of
passing an empty string that would break that env fallback.
"""

from __future__ import annotations

from typing import ClassVar

from app.llm.factory import ProviderConfig
from app.llm.providers import anthropic as ap
from app.llm.providers import azure as azp
from app.llm.providers import gemini as gp
from app.llm.providers import openai as op


class _Fake:
    last: ClassVar[dict] = {}

    def __init__(self, **kw):
        _Fake.last = kw


def test_anthropic_secret_then_env(monkeypatch):
    monkeypatch.setattr("langchain_anthropic.ChatAnthropic", _Fake)
    ap.build(ProviderConfig(provider="anthropic", secret_value="sk-A"), "m")
    assert _Fake.last["api_key"] == "sk-A"
    ap.build(ProviderConfig(provider="anthropic"), "m")
    assert "api_key" not in _Fake.last  # → ANTHROPIC_API_KEY from env


def test_openai_secret_then_env(monkeypatch):
    monkeypatch.setattr("langchain_openai.ChatOpenAI", _Fake)
    op.build(ProviderConfig(provider="openai", secret_value="sk-O"), "m")
    assert _Fake.last["api_key"] == "sk-O"
    op.build(ProviderConfig(provider="openai"), "m")
    assert "api_key" not in _Fake.last  # → OPENAI_API_KEY from env


def test_gemini_secret_then_env(monkeypatch):
    monkeypatch.setattr("langchain_google_genai.ChatGoogleGenerativeAI", _Fake)
    gp.build(ProviderConfig(provider="gemini", secret_value="sk-G"), "m")
    assert _Fake.last["google_api_key"] == "sk-G"
    gp.build(ProviderConfig(provider="gemini"), "m")
    assert "google_api_key" not in _Fake.last  # → GOOGLE_API_KEY from env


def test_azure_secret_and_endpoint_then_env(monkeypatch):
    monkeypatch.setattr("langchain_openai.AzureChatOpenAI", _Fake)
    azp.build(
        ProviderConfig(provider="azure", secret_value="sk-Z", endpoint="https://x.openai.azure.com"),
        "dep",
    )
    assert _Fake.last["api_key"] == "sk-Z"
    assert _Fake.last["azure_endpoint"] == "https://x.openai.azure.com"
    azp.build(ProviderConfig(provider="azure"), "dep")
    assert "api_key" not in _Fake.last  # → AZURE_OPENAI_API_KEY from env
    assert "azure_endpoint" not in _Fake.last  # → AZURE_OPENAI_ENDPOINT from env


def test_instance_default_does_not_leak_endpoint_or_region(monkeypatch):
    """The instance default must not push the Ollama URL / AWS region onto other
    providers — that would override their own env-based endpoint/region."""
    from app.config import settings
    from app.llm.factory import LLMProviderFactory

    f = LLMProviderFactory()
    monkeypatch.setattr(settings, "default_llm_provider", "azure")
    cfg = f._instance_default()
    assert cfg.provider == "azure" and cfg.endpoint is None and cfg.region is None
    monkeypatch.setattr(settings, "default_llm_provider", "vertex")
    assert f._instance_default().endpoint is None
    monkeypatch.setattr(settings, "default_llm_provider", "ollama")
    assert f._instance_default().endpoint == settings.ollama_endpoint
    monkeypatch.setattr(settings, "default_llm_provider", "bedrock")
    assert f._instance_default().region == settings.bedrock_region


def test_vertex_project_region_from_env_when_not_configured(monkeypatch):
    import pytest

    pytest.importorskip("langchain_google_vertexai")
    from app.llm.providers import vertex as vp

    monkeypatch.setattr("langchain_google_vertexai.model_garden.ChatAnthropicVertex", _Fake)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")
    monkeypatch.setenv("GOOGLE_CLOUD_REGION", "europe-west1")
    vp.build(ProviderConfig(provider="vertex"), "claude-x")
    assert _Fake.last["project"] == "my-proj"
    assert _Fake.last["location"] == "europe-west1"
