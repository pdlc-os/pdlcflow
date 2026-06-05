"""LLMProviderFactory — single entry point with two-level resolution.

Resolution order:
  1. Agent-level override     — agent_llm_config(org_id, agent_persona)
  2. Org default              — org_llm_config(org_id)
  3. Instance default         — PDLC_DEFAULT_LLM_PROVIDER env var
  4. Built-in fallback        — Bedrock with Claude opus/sonnet/haiku
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langchain_core.language_models import BaseChatModel

from ..config import settings
from .providers import (
    anthropic as anthropic_p,
    azure as azure_p,
    bedrock as bedrock_p,
    gemini as gemini_p,
    ollama as ollama_p,
    openai as openai_p,
    vertex as vertex_p,
)
from .tier_map import resolve_model_id

Provider = Literal[
    "bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama"
]
Tier = Literal["opus", "sonnet", "haiku"]

_BUILDERS = {
    "bedrock": bedrock_p.build,
    "anthropic": anthropic_p.build,
    "vertex": vertex_p.build,
    "azure": azure_p.build,
    "openai": openai_p.build,
    "gemini": gemini_p.build,
    "ollama": ollama_p.build,
}


@dataclass
class ProviderConfig:
    provider: Provider
    region: str | None = None
    endpoint: str | None = None
    secret_value: str | None = None
    tier_map_override: dict[str, str] | None = None
    model_id_override: str | None = None


@dataclass
class TenantCtx:
    org_id: str


class LLMProviderFactory:
    def __init__(self, db=None, secrets=None):
        self._db = db
        self._secrets = secrets

    def get_model(self, persona: str, tier: Tier, tenant: TenantCtx) -> BaseChatModel:
        cfg = (
            self._agent_override(tenant.org_id, persona)
            or self._org_default(tenant.org_id)
            or self._instance_default()
            or self._fallback()
        )
        model_id = cfg.model_id_override or resolve_model_id(
            cfg.provider, tier, cfg.tier_map_override
        )
        builder = _BUILDERS[cfg.provider]
        return builder(cfg, model_id)

    # ----- resolution sources (Phase A: settings-only; B wires DB lookups) -----
    def _agent_override(self, _org_id: str, _persona: str) -> ProviderConfig | None:
        return None

    def _org_default(self, _org_id: str) -> ProviderConfig | None:
        return None

    def _instance_default(self) -> ProviderConfig | None:
        return ProviderConfig(
            provider=settings.default_llm_provider,
            region=settings.bedrock_region,
            endpoint=settings.ollama_endpoint,
        )

    def _fallback(self) -> ProviderConfig:
        return ProviderConfig(provider="bedrock", region="us-east-1")
