from app.llm import LLMProviderFactory
from app.llm.tier_map import DEFAULT_TIER_MAP, resolve_model_id


def test_tier_map_covers_all_providers():
    expected = {"bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama"}
    assert set(DEFAULT_TIER_MAP.keys()) == expected
    for m in DEFAULT_TIER_MAP.values():
        assert set(m.keys()) == {"opus", "sonnet", "haiku"}


def test_resolve_model_id_default_path():
    # Anthropic family keeps Opus/Sonnet/Haiku; others auto-map the tier.
    assert resolve_model_id("anthropic", "opus") == "claude-opus-4-8"
    assert resolve_model_id("bedrock", "sonnet") == "anthropic.claude-sonnet-4-6"
    assert resolve_model_id("openai", "opus") == "gpt-5.5"        # highest capability
    assert resolve_model_id("openai", "sonnet") == "gpt-5.4"      # general purpose
    assert resolve_model_id("openai", "haiku") == "gpt-5.4-mini"  # low token
    assert resolve_model_id("gemini", "opus") == "gemini-3.1-pro"
    assert resolve_model_id("gemini", "haiku") == "gemini-3.1-flash-lite"


def test_resolve_model_id_override_wins():
    assert resolve_model_id("openai", "opus", {"opus": "o1", "sonnet": "x", "haiku": "y"}) == "o1"


def test_tiers_are_distinct_per_provider():
    # No provider should collapse two tiers onto the same model (defeats tiering).
    for provider, table in DEFAULT_TIER_MAP.items():
        assert len(set(table.values())) == 3, f"{provider} has duplicate tier models: {table}"


def test_factory_fallback_returns_bedrock_config():
    f = LLMProviderFactory()
    cfg = f._fallback()
    assert cfg.provider == "bedrock"


def test_persona_tier_flows_through_the_real_backend_to_the_factory():
    """End-to-end: complete(persona) → port resolves the persona's tier →
    FactoryCompletionBackend → factory.get_model(tier=...). A spy factory records
    the tier it was asked for, so we confirm each agent hits its declared tier."""
    from app.runtime.llm_backend import FactoryCompletionBackend
    from pdlc_graph.llm_port import (
        complete,
        reset_completion_backend,
        set_completion_backend,
    )

    seen: dict[str, str] = {}

    class _Result:
        content = "ok"

    class _Model:
        def invoke(self, _messages):
            return _Result()

    class _SpyFactory:
        def get_model(self, persona, tier, tenant):
            seen[persona] = tier
            return _Model()

    set_completion_backend(FactoryCompletionBackend(_SpyFactory(), org_id="t"))
    try:
        complete("sentinel", "evaluate")   # haiku
        complete("neo", "design")          # opus
        complete("muse", "ux")             # sonnet
    finally:
        reset_completion_backend()

    assert seen == {"sentinel": "haiku", "neo": "opus", "muse": "sonnet"}
