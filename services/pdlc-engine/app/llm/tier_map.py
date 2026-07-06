"""Tier → concrete model ID, per provider.

Agents declare a provider-neutral tier in their soul-spec frontmatter
(`tier: premium|balanced|economy`). The factory consults this map to resolve a
concrete provider-specific ID. Per-tenant `org_llm_config.tier_map` overrides
this; per-agent `agent_llm_config.model_id` short-circuits the lookup entirely.
"""

from __future__ import annotations

# Defaults pick the highest-capability current model for each tier per provider
# (as of 2026-06). premium = highest capability, balanced = general purpose,
# economy = low token / fast. All overridable per tenant via
# `org_llm_config.tier_map`, or per agent via `agent_llm_config.model_id`.
# Provider model IDs drift — verify for your account.
DEFAULT_TIER_MAP: dict[str, dict[str, str]] = {
    # Claude family — premium / balanced / economy = Opus / Sonnet / Haiku.
    "bedrock": {
        "premium":   "anthropic.claude-opus-4-8",
        "balanced": "anthropic.claude-sonnet-4-6",
        "economy":  "anthropic.claude-haiku-4-5",
    },
    "anthropic": {
        "premium":   "claude-opus-4-8",
        "balanced": "claude-sonnet-4-6",
        "economy":  "claude-haiku-4-5",
    },
    "vertex": {  # Claude on Vertex; some projects need an @version suffix — override if so.
        "premium":   "claude-opus-4-8",
        "balanced": "claude-sonnet-4-6",
        "economy":  "claude-haiku-4-5",
    },
    # OpenAI — GPT-5.5 flagship / GPT-5.4 workhorse / GPT-5.4 mini.
    "openai": {
        "premium":   "gpt-5.5",
        "balanced": "gpt-5.4",
        "economy":  "gpt-5.4-mini",
    },
    "azure": {  # deployment names are tenant-specific — override via org_llm_config.tier_map.
        "premium":   "gpt-5.5",
        "balanced": "gpt-5.4",
        "economy":  "gpt-5.4-mini",
    },
    # Gemini — 3.1 Pro (frontier reasoning) / 3.5 Flash (general) / 3.1 Flash-Lite (cheap).
    "gemini": {
        "premium":   "gemini-3.1-pro",
        "balanced": "gemini-3.5-flash",
        "economy":  "gemini-3.1-flash-lite",
    },
    # Ollama (local) — pick models you've pulled; sensible placeholders.
    "ollama": {
        "premium":   "llama3.3:70b",
        "balanced": "qwen2.5:32b",
        "economy":  "qwen2.5:7b",
    },
    # Subscription CLIs (single-user self-host) — the value is the CLI's --model.
    "claude_code": {
        "premium":  "opus",
        "balanced": "sonnet",
        "economy":  "haiku",
    },
    "codex": {
        "premium":  "gpt-5.5",
        "balanced": "gpt-5.4",
        "economy":  "gpt-5.4-mini",
    },
    "gemini_cli": {
        "premium":  "gemini-3.1-pro",
        "balanced": "gemini-3.5-flash",
        "economy":  "gemini-3.1-flash-lite",
    },
}


class ModelResolutionError(RuntimeError):
    """No model id can be resolved for (provider, tier) — a config error, not a
    crash: providers without a built-in map (openai_compatible) require an org
    tier_map or an agent model_id, enforced at config-write time by the admin
    API. Raised (instead of a bare KeyError) so a stale/partial config fails
    with an actionable message."""


def resolve_model_id(
    provider: str,
    tier: str,
    override: dict[str, str] | None = None,
) -> str:
    table = override or DEFAULT_TIER_MAP.get(provider)
    if not table:
        raise ModelResolutionError(
            f"provider {provider!r} has no built-in tier map; set the org tier_map "
            f"(or an agent model_id) in Settings → Models"
        )
    try:
        return table[tier]
    except KeyError:
        raise ModelResolutionError(
            f"tier_map for provider {provider!r} lacks tier {tier!r}"
        ) from None
