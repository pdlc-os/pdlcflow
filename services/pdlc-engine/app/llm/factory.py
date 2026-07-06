"""LLMProviderFactory — single entry point with two-level resolution.

Resolution order:
  1. Agent-level override     — agent_llm_config(org_id, agent_persona)
  2. Org default              — org_llm_config(org_id)
  3. Instance default         — PDLC_DEFAULT_LLM_PROVIDER env var
  4. Built-in fallback        — Bedrock with Claude (premium/balanced/economy)
"""

from __future__ import annotations

import time as _time
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
    openai_compatible as openai_compatible_p,
)
from .providers import (
    vertex as vertex_p,
)
from .tier_map import resolve_model_id

Provider = Literal[
    "bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama",
    "openai_compatible",
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
    "openai_compatible": openai_compatible_p.build,
    "claude_code": claude_code_p.build,
    "codex": codex_p.build,
    "gemini_cli": gemini_cli_p.build,
}


class SecretResolutionError(RuntimeError):
    """A tenant config points at a secret_ref that cannot be resolved.

    Deliberately fatal: falling back to the instance env key here would
    silently bill tenant traffic to the operator — exactly the bug BYOK fixes.
    The message never contains the ref or key material.
    """


# Resolved plaintext keyed by ref, with a monotonic expiry. Vault resolution is
# a network round-trip on the hottest path (every completion); Fernet decrypt is
# cheap but caching uniformly is harmless. Cross-replica staleness after a
# rotation is bounded by the TTL (PDLC_SECRET_CACHE_TTL_S, 0 disables caching).
_SECRET_CACHE: dict[str, tuple[str, float]] = {}


def invalidate_secret_cache(ref: str | None = None) -> None:
    """Drop one cached secret (by ref) or all (admin key PUT/DELETE handlers)."""
    if ref is None:
        _SECRET_CACHE.clear()
    else:
        _SECRET_CACHE.pop(ref, None)


# Org pricing overrides, cached briefly so cost labelling doesn't add a second
# DB round-trip per completion (PRD-07). {org_id: (overrides|None, expires)}.
_PRICING_CACHE: dict[str, tuple[dict | None, float]] = {}
_PRICING_TTL_S = 60.0


def invalidate_pricing_cache(org_id: str | None = None) -> None:
    if org_id is None:
        _PRICING_CACHE.clear()
    else:
        _PRICING_CACHE.pop(org_id, None)


@dataclass
class NetworkConfig:
    """Egress controls threaded into provider builders (PRD-08). proxy/CA are
    instance-level (operator domain); extra_headers are org-level relay-gateway
    routing hints (guardrailed at the API — never credentials)."""

    proxy_url: str | None = None
    no_proxy: tuple[str, ...] = ()
    ca_bundle: str | None = None
    extra_headers: dict[str, str] | None = None


def instance_network(extra_headers: dict[str, str] | None = None) -> NetworkConfig | None:
    """NetworkConfig from PDLC_EGRESS_* settings (+ optional org headers);
    None when nothing is configured, so builders skip all egress plumbing."""
    proxy = getattr(settings, "egress_proxy_url", None)
    ca = getattr(settings, "egress_ca_bundle", None)
    if not (proxy or ca or extra_headers):
        return None
    no_proxy = tuple(
        s.strip() for s in getattr(settings, "egress_no_proxy", "").split(",") if s.strip()
    )
    return NetworkConfig(proxy_url=proxy, no_proxy=no_proxy, ca_bundle=ca,
                         extra_headers=extra_headers or None)


@dataclass
class ProviderConfig:
    provider: Provider
    region: str | None = None
    endpoint: str | None = None
    secret_value: str | None = None
    tier_map_override: dict[str, str] | None = None
    model_id_override: str | None = None
    network: NetworkConfig | None = None


@dataclass
class TenantCtx:
    org_id: str


class LLMProviderFactory:
    def __init__(self, db=None, secrets=None):
        self._db = db
        self._secrets = secrets

    def get_model(self, persona: str, tier: Tier, tenant: TenantCtx) -> BaseChatModel:
        model, _provider, _model_id = self.resolve(persona, tier, tenant)
        return model

    def resolve(self, persona: str, tier: Tier, tenant: TenantCtx) -> tuple[BaseChatModel, str, str]:
        """Like get_model but also returns the resolved (provider, model_id) so
        callers (e.g. observability spans, cost estimation) can label the call."""
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
        return builder(cfg, model_id), cfg.provider, model_id

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
            # The COALESCE implements key inheritance: an override without its
            # own key borrows the org-default key, but ONLY when the providers
            # match — an Anthropic key must never be sent to OpenAI.
            row = conn.execute(
                text(
                    "select a.provider, a.model_id, a.region, a.endpoint, "
                    "o.extra_headers, "
                    "coalesce(a.secret_ref, case when o.provider = a.provider "
                    "then o.secret_ref end) as secret_ref "
                    "from agent_llm_config a "
                    "left join org_llm_config o on o.org_id = a.org_id "
                    "where a.org_id = :o and a.agent_persona = :p"
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
            secret_value=self._resolve_secret(row["secret_ref"]),
            network=instance_network(row["extra_headers"]),
        )

    def _org_default(self, org_id: str) -> ProviderConfig | None:
        if self._db is None or not self._is_org_uuid(org_id):
            return None
        from ..db.rls import set_org_context

        with self._db.begin() as conn:
            set_org_context(conn, org_id)
            row = conn.execute(
                text(
                    "select provider, region, endpoint, tier_map, secret_ref, "
                    "extra_headers from org_llm_config where org_id = :o"
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
            secret_value=self._resolve_secret(row["secret_ref"]),
            network=instance_network(row["extra_headers"]),
        )

    def pricing_overrides(self, org_id: str) -> dict | None:
        """The org's `pricing_override` sheet for estimate_usd (PRD-07), with a
        short TTL cache — admin PUTs call invalidate_pricing_cache()."""
        if self._db is None or not self._is_org_uuid(org_id):
            return None
        hit = _PRICING_CACHE.get(org_id)
        if hit is not None and hit[1] > _time.monotonic():
            return hit[0]
        from ..db.rls import set_org_context

        try:
            with self._db.begin() as conn:
                set_org_context(conn, org_id)
                value = conn.execute(
                    text("select pricing_override from org_llm_config where org_id = :o"),
                    {"o": org_id},
                ).scalar()
        except Exception:  # pricing must never break a completion
            value = None
        _PRICING_CACHE[org_id] = (value, _time.monotonic() + _PRICING_TTL_S)
        return value

    # ----- failover chain (PRD-05) -----
    # The primary candidate is always resolve()'s pick; these are candidates
    # 1..n, built LAZILY (per-entry secret resolution / model construction runs
    # only when the loop actually reaches that candidate, so one broken
    # fallback entry can't poison the healthy primary path). Queried on demand
    # — orgs without a chain pay no extra DB read on the hot path because the
    # backend only iterates past the primary after a retriable failure.

    def _failover_entries(self, org_id: str) -> tuple[list[dict], dict | None]:
        if self._db is None or not self._is_org_uuid(org_id):
            return [], None
        from ..db.rls import set_org_context

        with self._db.begin() as conn:
            set_org_context(conn, org_id)
            row = conn.execute(
                text("select failover_chain, extra_headers "
                     "from org_llm_config where org_id = :o"),
                {"o": org_id},
            ).mappings().first()
        if not row:
            return [], None
        return list(row["failover_chain"] or []), row["extra_headers"]

    def failover_candidates(self, tier: Tier, tenant: TenantCtx) -> list:
        """Zero-arg builders, one per chain entry; each returns
        (model, provider, model_id, endpoint). Order = admin intent."""
        if not getattr(settings, "llm_failover_enabled", True):
            return []
        builders = []
        entries, org_headers = self._failover_entries(tenant.org_id)
        for entry in entries:
            def _build(e=entry):
                cfg = ProviderConfig(
                    provider=e["provider"],
                    region=e.get("region"),
                    endpoint=e.get("endpoint"),
                    tier_map_override=e.get("tier_map"),
                    secret_value=self._resolve_secret(e.get("secret_ref")),
                    network=instance_network(org_headers),
                )
                self._guard_cli(cfg.provider)
                model_id = resolve_model_id(cfg.provider, tier, cfg.tier_map_override)
                return _BUILDERS[cfg.provider](cfg, model_id), cfg.provider, model_id, cfg.endpoint
            builders.append(_build)
        return builders

    def _resolve_secret(self, ref: str | None) -> str | None:
        """secret_ref → plaintext for the tenant path, with a TTL cache.

        A NULL ref legitimately means "no tenant key" → providers fall back to
        the instance env key. A non-null ref that will not resolve raises
        SecretResolutionError instead of falling back (see the class docstring).
        """
        if not ref:
            return None
        ttl = getattr(settings, "secret_cache_ttl_s", 300)
        if ttl > 0:
            hit = _SECRET_CACHE.get(ref)
            if hit is not None and hit[1] > _time.monotonic():
                return hit[0]
        try:
            if self._secrets is not None:
                secrets = self._secrets
            else:
                from ..secretstore import get_secrets

                secrets = get_secrets()
            value = secrets.resolve(ref)
        except Exception as exc:  # bad ciphertext, Vault down, backend misconfig
            raise SecretResolutionError(
                "tenant LLM key could not be resolved (secrets backend error); "
                "re-enter the key in Settings → Models or check the secrets backend"
            ) from exc
        if value is None:  # unknown/legacy ref shape, missing env var
            raise SecretResolutionError(
                "tenant LLM key could not be resolved (dangling secret_ref); "
                "re-enter the key in Settings → Models"
            )
        if ttl > 0:
            _SECRET_CACHE[ref] = (value, _time.monotonic() + ttl)
        return value

    def _instance_default(self) -> ProviderConfig | None:
        # Only attach region/endpoint to the provider that uses them, so we don't
        # leak the Ollama URL (or AWS region) into Azure/Vertex/etc., which would
        # override their own env-based endpoint/region.
        p = settings.default_llm_provider
        return ProviderConfig(
            provider=p,
            region=settings.bedrock_region if p == "bedrock" else None,
            endpoint=settings.ollama_endpoint if p == "ollama" else None,
            network=instance_network(),
        )

    def _fallback(self) -> ProviderConfig:
        return ProviderConfig(provider="bedrock", region="us-east-1",
                              network=instance_network())
