"""Tier → concrete model ID, per provider.

Agents declare a tier in their soul-spec frontmatter (`model: opus|sonnet|haiku`).
The factory consults this map to resolve to a concrete provider-specific ID.
Per-tenant `org_llm_config.tier_map` overrides this; per-agent
`agent_llm_config.model_id` short-circuits the lookup entirely.
"""

from __future__ import annotations

# Defaults pick the highest-capability current model for each tier per provider
# (as of 2026-06). opus = frontier, sonnet = general-purpose, haiku = cheap/fast.
# All overridable per tenant via `org_llm_config.tier_map`, or per agent via
# `agent_llm_config.model_id`. Provider model IDs drift — verify for your account.
DEFAULT_TIER_MAP: dict[str, dict[str, str]] = {
    # Claude family — Opus / Sonnet / Haiku map straight to the tiers.
    "bedrock": {
        "opus":   "anthropic.claude-opus-4-8",
        "sonnet": "anthropic.claude-sonnet-4-6",
        "haiku":  "anthropic.claude-haiku-4-5",
    },
    "anthropic": {
        "opus":   "claude-opus-4-8",
        "sonnet": "claude-sonnet-4-6",
        "haiku":  "claude-haiku-4-5",
    },
    "vertex": {  # Claude on Vertex; some projects need an @version suffix — override if so.
        "opus":   "claude-opus-4-8",
        "sonnet": "claude-sonnet-4-6",
        "haiku":  "claude-haiku-4-5",
    },
    # OpenAI — GPT-5.5 flagship / GPT-5.4 workhorse / GPT-5.4 mini.
    "openai": {
        "opus":   "gpt-5.5",
        "sonnet": "gpt-5.4",
        "haiku":  "gpt-5.4-mini",
    },
    "azure": {  # deployment names are tenant-specific — override via org_llm_config.tier_map.
        "opus":   "gpt-5.5",
        "sonnet": "gpt-5.4",
        "haiku":  "gpt-5.4-mini",
    },
    # Gemini — 3.1 Pro (frontier reasoning) / 3.5 Flash (general) / 3.1 Flash-Lite (cheap).
    "gemini": {
        "opus":   "gemini-3.1-pro",
        "sonnet": "gemini-3.5-flash",
        "haiku":  "gemini-3.1-flash-lite",
    },
    # Ollama (local) — pick models you've pulled; sensible placeholders.
    "ollama": {
        "opus":   "llama3.3:70b",
        "sonnet": "qwen2.5:32b",
        "haiku":  "qwen2.5:7b",
    },
}


def resolve_model_id(
    provider: str,
    tier: str,
    override: dict[str, str] | None = None,
) -> str:
    table = override or DEFAULT_TIER_MAP[provider]
    return table[tier]
