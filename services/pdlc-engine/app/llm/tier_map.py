"""Tier → concrete model ID, per provider.

Agents declare a tier in their soul-spec frontmatter (`model: opus|sonnet|haiku`).
The factory consults this map to resolve to a concrete provider-specific ID.
Per-tenant `org_llm_config.tier_map` overrides this; per-agent
`agent_llm_config.model_id` short-circuits the lookup entirely.
"""

from __future__ import annotations

DEFAULT_TIER_MAP: dict[str, dict[str, str]] = {
    "bedrock": {
        "opus":   "anthropic.claude-opus-4-7",
        "sonnet": "anthropic.claude-sonnet-4-6",
        "haiku":  "anthropic.claude-haiku-4-5",
    },
    "anthropic": {
        "opus":   "claude-opus-4-7",
        "sonnet": "claude-sonnet-4-6",
        "haiku":  "claude-haiku-4-5",
    },
    "vertex": {
        "opus":   "claude-opus-4@20260101",
        "sonnet": "claude-sonnet-4@20260101",
        "haiku":  "claude-haiku-4@20260101",
    },
    "azure": {
        "opus":   "gpt-4o",
        "sonnet": "gpt-4o-mini",
        "haiku":  "gpt-4o-mini",
    },
    "openai": {
        "opus":   "gpt-4o",
        "sonnet": "gpt-4o-mini",
        "haiku":  "gpt-4o-mini",
    },
    "gemini": {
        "opus":   "gemini-2.5-pro",
        "sonnet": "gemini-2.0-flash",
        "haiku":  "gemini-2.0-flash-lite",
    },
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
