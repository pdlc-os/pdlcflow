from app.llm import LLMProviderFactory
from app.llm.factory import TenantCtx
from app.llm.tier_map import DEFAULT_TIER_MAP, resolve_model_id


def test_tier_map_covers_all_providers():
    expected = {"bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama"}
    assert set(DEFAULT_TIER_MAP.keys()) == expected
    for provider, m in DEFAULT_TIER_MAP.items():
        assert set(m.keys()) == {"opus", "sonnet", "haiku"}


def test_resolve_model_id_default_path():
    assert resolve_model_id("bedrock", "opus") == "anthropic.claude-opus-4-7"
    assert resolve_model_id("openai", "haiku") == "gpt-4o-mini"


def test_resolve_model_id_override_wins():
    assert resolve_model_id("openai", "opus", {"opus": "o1", "sonnet": "x", "haiku": "y"}) == "o1"


def test_factory_fallback_returns_bedrock_config():
    f = LLMProviderFactory()
    cfg = f._fallback()
    assert cfg.provider == "bedrock"
