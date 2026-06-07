"""LLMProviderFactory — single entry point with two-level resolution.

Resolution order:
  1. Agent-level override     — agent_llm_config(org_id, agent_persona)
  2. Org default              — org_llm_config(org_id)
  3. Instance default         — PDLC_DEFAULT_LLM_PROVIDER env var
  4. Built-in fallback        — Bedrock with Claude (premium/balanced/economy)
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from typing import Literal

from langchain_core.language_models import BaseChatModel
from sqlalchemy import text

from ..config import settings
from .providers import (
    anthropic as anthropic_p,
)
from .providers import (
    azure as azure_p,
)
from .providers import (
    bedrock as bedrock_p,
)
from .providers import (
    claude_code as claude_code_p,
)
from .providers import (
    codex as codex_p,
)
from .providers import (
    gemini as gemini_p,
)
from .providers import (
    gemini_cli as gemini_cli_p,
)
from .providers import (
    ollama as ollama_p,
)
from .providers import (
    openai as openai_p,
)
from .providers import (
    vertex as vertex_p,
)
from .tier_map import resolve_model_id

Provider = Literal[
    "bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama",
    "claude_code", "codex", "gemini_cli",
]
Tier = Literal["premium", "balanced", "economy"]

# Subscription-backed local CLIs — single-user self-host only (see _guard_cli).
CLI_PROVIDERS = {"claude_code", "codex", "gemini_cli"}

_BUILDERS = {
    "bedrock": bedrock_p.build,
    "anthropic": anthropic_p.build,
    "vertex": vertex_p.build,
    "azure": azure_p.build,
    "openai": openai_p.build,
    "gemini": gemini_p.build,
    "ollama": ollama_p.build,
    "claude_code": claude_code_p.build,
    "codex": codex_p.build,
    "gemini_cli": gemini_cli_p.build,
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
        self._guard_cli(cfg.provider)
        model_id = cfg.model_id_override or resolve_model_id(
            cfg.provider, tier, cfg.tier_map_override
        )
        builder = _BUILDERS[cfg.provider]
        return builder(cfg, model_id)

    @staticmethod
    def _guard_cli(provider: str) -> None:
        """Subscription CLIs are single-user self-host only: opt-in + no auth."""
        if provider not in CLI_PROVIDERS:
            return
        if not getattr(settings, "enable_cli_providers", False):
            raise ValueError(
                f"LLM provider {provider!r} is a subscription CLI; set "
                f"PDLC_ENABLE_CLI_PROVIDERS=true (single-user self-host only)."
            )
        if getattr(settings, "auth_required", False):
            raise ValueError(
                f"LLM provider {provider!r} is not allowed in multi-user / SaaS mode "
                f"(PDLC_AUTH_REQUIRED is on) — it can only bill one local subscription."
            )

    # ----- resolution sources -----
    # Per-tenant / per-agent config lives in org_llm_config / agent_llm_config
    # (RLS-FORCEd). When the factory has a DB engine and a real org UUID, these
    # take effect; otherwise (self-host / no DB) we fall through to the env default.
    @staticmethod
    def _is_org_uuid(org_id: str) -> bool:
        try:
            _uuid.UUID(str(org_id))
            return True
        except (ValueError, TypeError):
            return False

    def _agent_override(self, org_id: str, persona: str) -> ProviderConfig | None:
        if self._db is None or not self._is_org_uuid(org_id):
            return None
        from ..db.rls import set_org_context

        with self._db.begin() as conn:
            set_org_context(conn, org_id)
            row = conn.execute(
                text(
                    "select provider, model_id, region, endpoint "
                    "from agent_llm_config where org_id = :o and agent_persona = :p"
                ),
                {"o": org_id, "p": persona},
            ).mappings().first()
        if not row:
            return None
        return ProviderConfig(
            provider=row["provider"],
            model_id_override=row["model_id"],
            region=row["region"],
            endpoint=row["endpoint"],
        )

    def _org_default(self, org_id: str) -> ProviderConfig | None:
        if self._db is None or not self._is_org_uuid(org_id):
            return None
        from ..db.rls import set_org_context

        with self._db.begin() as conn:
            set_org_context(conn, org_id)
            row = conn.execute(
                text(
                    "select provider, region, endpoint, tier_map "
                    "from org_llm_config where org_id = :o"
                ),
                {"o": org_id},
            ).mappings().first()
        if not row:
            return None
        return ProviderConfig(
            provider=row["provider"],
            region=row["region"],
            endpoint=row["endpoint"],
            tier_map_override=row["tier_map"],
        )

    def _instance_default(self) -> ProviderConfig | None:
        # Only attach region/endpoint to the provider that uses them, so we don't
        # leak the Ollama URL (or AWS region) into Azure/Vertex/etc., which would
        # override their own env-based endpoint/region.
        p = settings.default_llm_provider
        return ProviderConfig(
            provider=p,
            region=settings.bedrock_region if p == "bedrock" else None,
            endpoint=settings.ollama_endpoint if p == "ollama" else None,
        )

    def _fallback(self) -> ProviderConfig:
        return ProviderConfig(provider="bedrock", region="us-east-1")
