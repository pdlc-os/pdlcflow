"""Nexus Console — Models settings: org default + per-agent overrides.

Persists to org_llm_config / agent_llm_config (RLS-FORCEd, scoped to the admin's
org). The LLM factory reads these so per-tenant / per-agent model selection takes
effect. Tiers are provider-neutral (premium / balanced / economy); the factory's
tier_map turns a tier into a concrete model for the chosen provider.

BYOK: PUT bodies accept a WRITE-ONLY `api_key`. When present it is stored via the
secrets backend and only the resulting `secret_ref` is persisted; the plaintext
key is never written to the DB, logs, events, or any response. GET responses
expose only a derived `has_key` flag — not the key, not even the ref (an `enc:`
ref IS the ciphertext). Omitting `api_key` on PUT leaves any stored key intact,
so editing the provider/model never silently wipes credentials.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from ...auth.local import Identity, get_principal
from ...config import settings
from ...db.rls import set_org_context
from ...db.session import get_sync_engine
from ...llm import probe
from ...llm.factory import (
    LLMProviderFactory,
    ProviderConfig,
    SecretResolutionError,
    invalidate_secret_cache,
)
from ...llm.tier_map import resolve_model_id
from ._guard import admin_org

router = APIRouter(prefix="/models", tags=["admin", "models"])

Provider = Literal[
    "bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama",
    "openai_compatible",
]
Persona = Literal[
    "atlas", "bolt", "echo", "friday", "jarvis",
    "muse", "neo", "phantom", "pulse", "sentinel",
]


# ---------------------------------------------------------------------------
# Preset catalog (PRD-04) — curated vendored data; read-only + one-click apply.
# ---------------------------------------------------------------------------


def _preset_public(p) -> dict:
    """Catalog entry as the console sees it (pricing_hints stay server-side)."""
    return {
        "id": p.id, "label": p.label, "provider": p.provider,
        "endpoint": p.endpoint, "region": p.region, "tier_map": p.tier_map,
        "docs_url": p.docs_url, "key_hint": p.key_hint, "tags": p.tags,
        "needs_secret": p.needs_secret,
    }


@router.get("/presets")
def list_presets(
    q: str | None = None,
    org_id: str = Depends(admin_org("/admin/models/presets")),
) -> dict:
    from ...llm.presets import load_catalog

    catalog = load_catalog()
    return {
        "catalog_version": catalog.catalog_version,
        "presets": [_preset_public(p) for p in catalog.search(q)],
    }


@router.post("/presets/{preset_id}/apply")
def apply_preset(
    preset_id: str,
    org_id: str = Depends(admin_org("/admin/models/presets")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    """Upsert the org default from a curated preset (endpoints in the vendored
    catalog are trusted — tenant-typed endpoints go through the SSRF guard on
    the normal PUT instead). Never touches secret_ref; the console chains the
    key-entry PUT when needs_secret."""
    from ...llm.presets import load_catalog

    preset = load_catalog().get(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="unknown preset")
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        record_version(conn, org_id, "org", "preset_apply", principal)
        conn.execute(
            text(
                "insert into org_llm_config (org_id, provider, region, endpoint, tier_map) "
                "values (:o, :p, :r, :e, cast(:t as jsonb)) "
                "on conflict (org_id) do update set "
                "provider = excluded.provider, region = excluded.region, "
                "endpoint = excluded.endpoint, tier_map = excluded.tier_map"
            ),
            {"o": org_id, "p": preset.provider, "r": preset.region,
             "e": preset.endpoint, "t": json.dumps(preset.tier_map)},
        )
    _audit("admin.preset.applied", org_id, {"preset": preset.id, "provider": preset.provider})
    return {
        "ok": True,
        "applied": {"provider": preset.provider, "endpoint": preset.endpoint,
                    "region": preset.region, "tier_map": preset.tier_map},
        "needs_secret": preset.needs_secret,
    }


class FallbackEntry(BaseModel):
    """One failover-chain candidate (PRD-05). api_key is WRITE-ONLY; omitting
    it carries over the entry's previously stored key when the provider at the
    same position is unchanged."""

    provider: Provider
    region: str | None = None
    endpoint: str | None = None
    tier_map: dict[str, str] | None = None
    api_key: str | None = Field(None, min_length=1)


class FallbackEntryOut(BaseModel):
    provider: Provider
    region: str | None = None
    endpoint: str | None = None
    tier_map: dict[str, str] | None = None
    has_key: bool = False


class OrgDefault(BaseModel):
    provider: Provider
    tier_map: dict[str, str]  # {"premium": "...", "balanced": "...", "economy": "..."}
    region: str | None = None
    endpoint: str | None = None
    # WRITE-ONLY: accepted on PUT, stored via the secrets backend, never echoed.
    # None ⇒ keep whatever key is already stored.
    api_key: str | None = Field(None, min_length=1)
    # Ordered fallback candidates tried on retriable primary failures.
    failover_chain: list[FallbackEntry] = Field(default_factory=list, max_length=3)


class OrgDefaultOut(BaseModel):
    """GET response — physically lacks key fields so they cannot leak."""

    provider: Provider
    tier_map: dict[str, str]
    region: str | None = None
    endpoint: str | None = None
    has_key: bool = False
    failover_chain: list[FallbackEntryOut] = Field(default_factory=list)


class AgentOverride(BaseModel):
    agent_persona: Persona
    provider: Provider
    model_id: str
    region: str | None = None
    endpoint: str | None = None
    api_key: str | None = Field(None, min_length=1)  # WRITE-ONLY (see OrgDefault)


class AgentOverrideOut(BaseModel):
    agent_persona: Persona
    provider: Provider
    model_id: str
    region: str | None = None
    endpoint: str | None = None
    has_key: bool = False


def _engine():
    return get_sync_engine(settings)


_TIERS = ("premium", "balanced", "economy")


def _validate_provider_config(
    provider: str,
    endpoint: str | None,
    *,
    tier_map: dict[str, str] | None = None,
) -> None:
    """Config-write-time guards, so misconfig fails at PUT — not mid-turn.

    openai_compatible has no built-in tier map and no meaningful env-key
    fallback, so it must arrive complete; any tenant-supplied endpoint is
    checked against the SSRF egress policy before it can be stored.
    """
    if provider == "openai_compatible":
        if not endpoint:
            raise HTTPException(
                status_code=422,
                detail="openai_compatible requires an endpoint (base_url)")
        if tier_map is not None and (set(tier_map) != set(_TIERS)
                                     or not all(tier_map.values())):
            raise HTTPException(
                status_code=422,
                detail="openai_compatible requires a complete tier_map "
                       "(premium/balanced/economy) — there is no built-in default")
    if endpoint:
        try:
            probe.validate_endpoint(endpoint)
        except probe.EndpointNotAllowed as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


# Providers whose builders fall back to the OPERATOR's env key when no tenant
# key is present — a chain entry without its own key would silently downgrade
# the tenant to the instance credentials, so it's rejected at write time.
# (bedrock/vertex/ollama are keyless; openai_compatible has NO env fallback by
# design, so keyless entries are safe there — local vLLM/LiteLLM.)
_ENV_KEYED_PROVIDERS = {"anthropic", "openai", "gemini", "azure"}


def _validate_chain(entries: list[FallbackEntry]) -> None:
    """DB-free validation pass — runs before anything is read or stored."""
    for i, entry in enumerate(entries):
        _validate_provider_config(entry.provider, entry.endpoint,
                                  tier_map=entry.tier_map)
        if entry.provider == "openai_compatible" and entry.tier_map is None:
            raise HTTPException(
                status_code=422,
                detail=f"failover_chain[{i}]: openai_compatible requires a tier_map")


def _build_chain(org_id: str, entries: list[FallbackEntry],
                 existing: list[dict]) -> list[dict]:
    """Persist-shape the (already validated) chain. Keys entered as api_key are
    stored via the secretstore; omitted keys carry over from the existing chain
    at the same position when the provider is unchanged."""
    chain: list[dict] = []
    for i, entry in enumerate(entries):
        secret_ref = None
        if entry.api_key is not None:
            secret_ref = _store_key(entry.api_key, hint=f"llm/org/{org_id}/chain/{i}")
            invalidate_secret_cache(secret_ref)
        elif (i < len(existing)
              and existing[i].get("provider") == entry.provider):
            secret_ref = existing[i].get("secret_ref")
        if secret_ref is None and entry.provider in _ENV_KEYED_PROVIDERS:
            raise HTTPException(
                status_code=422,
                detail=f"failover_chain[{i}]: {entry.provider} requires api_key — "
                       "a fallback must not silently bill the operator's env key")
        chain.append({
            "provider": entry.provider, "region": entry.region,
            "endpoint": entry.endpoint, "tier_map": entry.tier_map,
            "secret_ref": secret_ref,
        })
    return chain


def _chain_out(chain: list[dict]) -> list[FallbackEntryOut]:
    return [FallbackEntryOut(
        provider=e["provider"], region=e.get("region"), endpoint=e.get("endpoint"),
        tier_map=e.get("tier_map"), has_key=bool(e.get("secret_ref")),
    ) for e in chain or []]


@router.get("/defaults")
def model_defaults(
    org_id: str = Depends(admin_org("/admin/models/defaults")),
) -> dict:
    """Read-only lists the console renders from: pickable providers (CLI
    providers excluded — single-user self-host only), personas, the built-in
    tier maps for prefill, and what the instance falls back to when the org has
    no row of its own."""
    from ...llm.tier_map import DEFAULT_TIER_MAP

    providers = list(Provider.__args__)  # type: ignore[attr-defined]
    p = settings.default_llm_provider
    return {
        "providers": providers,
        "personas": list(Persona.__args__),  # type: ignore[attr-defined]
        # openai_compatible has no built-in map — the console starts it blank
        # (or prefilled from a preset).
        "tier_maps": {name: DEFAULT_TIER_MAP[name]
                      for name in providers if name in DEFAULT_TIER_MAP},
        "instance_default": {
            "provider": p,
            "region": settings.bedrock_region if p == "bedrock" else None,
        },
    }


def _store_key(api_key: str, hint: str) -> str:
    """Store a tenant key in the secrets backend; return the opaque ref."""
    from ...secretstore import get_secrets

    try:
        return get_secrets().put(api_key, hint=hint)
    except Exception as exc:
        # Typically: PDLC_SECRETS_BACKEND=encrypted without PDLC_SECRET_KEY.
        raise HTTPException(
            status_code=503,
            detail="secrets backend unavailable — check PDLC_SECRETS_BACKEND / "
            "PDLC_SECRET_KEY before storing tenant API keys",
        ) from exc


# ---------------------------------------------------------------------------
# Config versioning (PRD-06). Every mutation records the FULL PRIOR state in
# llm_config_versions IN THE SAME TRANSACTION — no drift possible. Snapshots
# store secret_ref as-is (refs, never values — same trust boundary as the
# config tables); the export boundary is where refs get transformed/stripped
# (see models_versions.py).
# ---------------------------------------------------------------------------


def _read_current_config(conn, org_id: str, scope: str) -> dict | None:
    """Live row for a scope ('org' or a persona name), as a plain dict."""
    if scope == "org":
        row = conn.execute(
            text("select provider, region, endpoint, tier_map, secret_ref, "
                 "failover_chain from org_llm_config where org_id = :o"),
            {"o": org_id},
        ).mappings().first()
    else:
        row = conn.execute(
            text("select provider, model_id, region, endpoint, secret_ref "
                 "from agent_llm_config where org_id = :o and agent_persona = :p"),
            {"o": org_id, "p": scope},
        ).mappings().first()
    return dict(row) if row else None


def record_version(conn, org_id: str, scope: str, change_kind: str,
                   principal: Identity | None = None) -> None:
    prior = _read_current_config(conn, org_id, scope)
    actor_uid = None
    if principal is not None:
        try:
            actor_uid = str(uuid.UUID(str(principal.user_id)))
        except (ValueError, TypeError):
            actor_uid = None
    conn.execute(
        text("insert into llm_config_versions "
             "(id, org_id, scope, change_kind, snapshot, actor_user_id, actor_label) "
             "values (:i, :o, :s, :k, cast(:sn as jsonb), :au, :al)"),
        {"i": str(uuid.uuid4()), "o": org_id, "s": scope, "k": change_kind,
         "sn": json.dumps(prior) if prior is not None else None,
         "au": actor_uid, "al": principal.email if principal else None},
    )
    # Count-based retention, oldest-first (FR-9).
    conn.execute(
        text("delete from llm_config_versions where org_id = :o and scope = :s "
             "and id not in (select id from llm_config_versions "
             "where org_id = :o and scope = :s "
             "order by created_at desc, id desc limit :keep)"),
        {"o": org_id, "s": scope,
         "keep": getattr(settings, "llm_config_version_keep", 50)},
    )


def _audit(event_type: str, org_id: str, payload: dict) -> None:
    """Best-effort clickstream audit for key lifecycle — never key material."""
    try:
        from ...clickstream.emitter import get_emitter

        get_emitter().emit(
            event_type,
            {"org_id": uuid.UUID(str(org_id)), "project_id": uuid.UUID(int=0),
             "actor": "admin"},
            payload,
            correlation_id=str(uuid.uuid4()),
        )
    except Exception:  # audit must never fail the admin call
        pass


@router.get("/org-default", response_model=OrgDefaultOut | None)
def get_org_default(
    org_id: str = Depends(admin_org("/admin/models/org-default")),
) -> OrgDefaultOut | None:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        row = conn.execute(
            text("select provider, tier_map, region, endpoint, "
                 "secret_ref is not null as has_key, failover_chain "
                 "from org_llm_config where org_id = :o"),
            {"o": org_id},
        ).mappings().first()
    if not row:
        return None
    data = dict(row)
    data["failover_chain"] = _chain_out(data.get("failover_chain") or [])
    return OrgDefaultOut(**data)


@router.put("/org-default")
def set_org_default(
    cfg: OrgDefault,
    org_id: str = Depends(admin_org("/admin/models/org-default")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    _validate_provider_config(cfg.provider, cfg.endpoint, tier_map=cfg.tier_map)
    _validate_chain(cfg.failover_chain)
    # Existing chain is needed for key carryover (only when a chain is sent).
    existing_chain: list = []
    if cfg.failover_chain:
        with _engine().begin() as conn:
            set_org_context(conn, org_id)
            existing_chain = list(conn.execute(
                text("select failover_chain from org_llm_config where org_id = :o"),
                {"o": org_id},
            ).scalar() or [])
    chain = _build_chain(org_id, cfg.failover_chain, existing_chain)
    params = {"o": org_id, "p": cfg.provider, "r": cfg.region, "e": cfg.endpoint,
              "t": json.dumps(cfg.tier_map), "fc": json.dumps(chain)}
    if cfg.api_key is not None:
        ref = _store_key(cfg.api_key, hint=f"llm/org/{org_id}")
        invalidate_secret_cache(ref)  # vault refs are stable paths — drop stale plaintext
        params["sr"] = ref
        sql = (
            "insert into org_llm_config "
            "(org_id, provider, region, endpoint, tier_map, failover_chain, secret_ref) "
            "values (:o, :p, :r, :e, cast(:t as jsonb), cast(:fc as jsonb), :sr) "
            "on conflict (org_id) do update set "
            "provider = excluded.provider, region = excluded.region, "
            "endpoint = excluded.endpoint, tier_map = excluded.tier_map, "
            "failover_chain = excluded.failover_chain, "
            "secret_ref = excluded.secret_ref"
        )
    else:
        # api_key omitted ⇒ leave secret_ref untouched (edits must not wipe keys).
        sql = (
            "insert into org_llm_config "
            "(org_id, provider, region, endpoint, tier_map, failover_chain) "
            "values (:o, :p, :r, :e, cast(:t as jsonb), cast(:fc as jsonb)) "
            "on conflict (org_id) do update set "
            "provider = excluded.provider, region = excluded.region, "
            "endpoint = excluded.endpoint, tier_map = excluded.tier_map, "
            "failover_chain = excluded.failover_chain"
        )
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        record_version(conn, org_id, "org", "update", principal)
        conn.execute(text(sql), params)
        has_key = bool(conn.execute(
            text("select secret_ref is not null from org_llm_config where org_id = :o"),
            {"o": org_id},
        ).scalar())
    if cfg.api_key is not None:
        _audit("admin.llm_key.set", org_id,
               {"scope": "org-default", "provider": cfg.provider})
    _audit("llm_config.changed", org_id, {"scope": "org", "change_kind": "update"})
    return {"ok": True, "has_key": has_key}


@router.delete("/org-default/key")
def clear_org_default_key(
    org_id: str = Depends(admin_org("/admin/models/org-default")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        record_version(conn, org_id, "org", "update", principal)
        conn.execute(
            text("update org_llm_config set secret_ref = null where org_id = :o"),
            {"o": org_id},
        )
    invalidate_secret_cache()
    _audit("admin.llm_key.cleared", org_id, {"scope": "org-default"})
    return {"ok": True}


@router.get("/agent-overrides", response_model=list[AgentOverrideOut])
def list_agent_overrides(
    org_id: str = Depends(admin_org("/admin/models/agent-overrides")),
) -> list[AgentOverrideOut]:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        rows = conn.execute(
            text("select agent_persona, provider, model_id, region, endpoint, "
                 "secret_ref is not null as has_key "
                 "from agent_llm_config where org_id = :o order by agent_persona"),
            {"o": org_id},
        ).mappings().all()
    return [AgentOverrideOut(**r) for r in rows]


@router.put("/agent-overrides/{persona}")
def set_agent_override(
    persona: Persona,
    cfg: AgentOverride,
    org_id: str = Depends(admin_org("/admin/models/agent-overrides")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    _validate_provider_config(cfg.provider, cfg.endpoint)  # model_id is required by schema
    params = {"o": org_id, "a": persona, "p": cfg.provider, "m": cfg.model_id,
              "r": cfg.region, "e": cfg.endpoint}
    if cfg.api_key is not None:
        ref = _store_key(cfg.api_key, hint=f"llm/agent/{org_id}/{persona}")
        invalidate_secret_cache(ref)
        params["sr"] = ref
        sql = (
            "insert into agent_llm_config "
            "(org_id, agent_persona, provider, model_id, region, endpoint, secret_ref) "
            "values (:o, :a, :p, :m, :r, :e, :sr) "
            "on conflict (org_id, agent_persona) do update set "
            "provider = excluded.provider, model_id = excluded.model_id, "
            "region = excluded.region, endpoint = excluded.endpoint, "
            "secret_ref = excluded.secret_ref"
        )
    else:
        sql = (
            "insert into agent_llm_config "
            "(org_id, agent_persona, provider, model_id, region, endpoint) "
            "values (:o, :a, :p, :m, :r, :e) "
            "on conflict (org_id, agent_persona) do update set "
            "provider = excluded.provider, model_id = excluded.model_id, "
            "region = excluded.region, endpoint = excluded.endpoint"
        )
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        record_version(conn, org_id, persona, "update", principal)
        conn.execute(text(sql), params)
        has_key = bool(conn.execute(
            text("select secret_ref is not null from agent_llm_config "
                 "where org_id = :o and agent_persona = :a"),
            {"o": org_id, "a": persona},
        ).scalar())
    if cfg.api_key is not None:
        _audit("admin.llm_key.set", org_id,
               {"scope": "agent-override", "persona": persona, "provider": cfg.provider})
    _audit("llm_config.changed", org_id, {"scope": persona, "change_kind": "update"})
    return {"ok": True, "persona": persona, "has_key": has_key}


@router.delete("/agent-overrides/{persona}/key")
def clear_agent_override_key(
    persona: Persona,
    org_id: str = Depends(admin_org("/admin/models/agent-overrides")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        record_version(conn, org_id, persona, "update", principal)
        conn.execute(
            text("update agent_llm_config set secret_ref = null "
                 "where org_id = :o and agent_persona = :a"),
            {"o": org_id, "a": persona},
        )
    invalidate_secret_cache()
    _audit("admin.llm_key.cleared", org_id,
           {"scope": "agent-override", "persona": persona})
    return {"ok": True, "persona": persona}


# ---------------------------------------------------------------------------
# Provider connectivity testing (PRD-03). POST /test probes a CANDIDATE config
# (pre-save, from the console form) or the SAVED config for a scope; the last
# scoped result is persisted for the console's status chips (GET /health).
# ---------------------------------------------------------------------------


class ProbeRequest(BaseModel):
    # Candidate test: provider (+ optional model_id/tier/region/endpoint/api_key).
    provider: Provider | None = None
    model_id: str | None = None
    tier: Literal["premium", "balanced", "economy"] | None = None
    region: str | None = None
    endpoint: str | None = None
    api_key: str | None = Field(None, min_length=1)  # WRITE-ONLY, used once, discarded
    # Saved-config test: scope = "org-default" | "agent:<persona>".
    scope: str | None = None
    use_saved_key: bool = False


def _load_scope_config(org_id: str, req: ProbeRequest) -> tuple[ProviderConfig, str]:
    """Build (ProviderConfig, model_id) from the SAVED row for req.scope."""
    if req.scope == "org-default":
        with _engine().begin() as conn:
            set_org_context(conn, org_id)
            row = conn.execute(
                text("select provider, region, endpoint, tier_map, secret_ref "
                     "from org_llm_config where org_id = :o"),
                {"o": org_id},
            ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="no org-default config saved")
        model_id = req.model_id or resolve_model_id(
            row["provider"], req.tier or "balanced", row["tier_map"])
    elif req.scope and req.scope.startswith("agent:"):
        persona = req.scope.split(":", 1)[1]
        with _engine().begin() as conn:
            set_org_context(conn, org_id)
            # Same COALESCE key inheritance as the factory's _agent_override.
            row = conn.execute(
                text("select a.provider, a.model_id, a.region, a.endpoint, "
                     "coalesce(a.secret_ref, case when o.provider = a.provider "
                     "then o.secret_ref end) as secret_ref "
                     "from agent_llm_config a "
                     "left join org_llm_config o on o.org_id = a.org_id "
                     "where a.org_id = :o and a.agent_persona = :p"),
                {"o": org_id, "p": persona},
            ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="no override saved for that persona")
        model_id = req.model_id or row["model_id"]
    else:
        raise HTTPException(status_code=422,
                            detail="scope must be 'org-default' or 'agent:<persona>'")

    secret_value = req.api_key  # inline key takes precedence (pre-rotation test)
    if secret_value is None and req.use_saved_key and row["secret_ref"]:
        # Same resolution (and cache) the real call path uses.
        secret_value = LLMProviderFactory()._resolve_secret(row["secret_ref"])
    return ProviderConfig(
        provider=row["provider"], region=row["region"], endpoint=row["endpoint"],
        secret_value=secret_value,
    ), model_id


def _persist_health(org_id: str, scope: str, provider: str, r: probe.ProbeResult) -> None:
    """Best-effort — a failed chip write must not fail the probe response."""
    try:
        with _engine().begin() as conn:
            set_org_context(conn, org_id)
            conn.execute(
                text("insert into llm_provider_health "
                     "(org_id, scope, provider, ok, latency_ms, error_class, checked_at) "
                     "values (:o, :s, :p, :k, :l, :e, now()) "
                     "on conflict (org_id, scope) do update set "
                     "provider = excluded.provider, ok = excluded.ok, "
                     "latency_ms = excluded.latency_ms, "
                     "error_class = excluded.error_class, "
                     "checked_at = excluded.checked_at"),
                {"o": org_id, "s": scope, "p": provider, "k": r.ok,
                 "l": r.latency_ms, "e": r.error_class},
            )
    except Exception:
        pass


@router.post("/test")
def test_provider(
    req: ProbeRequest, org_id: str = Depends(admin_org("/admin/models/test"))
) -> dict:
    if not probe.probe_allowed(org_id):
        raise HTTPException(status_code=429,
                            detail=f"probe limit {probe.PROBE_LIMIT_PER_MIN}/min per org")
    if req.scope is not None:
        try:
            cfg, model_id = _load_scope_config(org_id, req)
        except SecretResolutionError:
            result = probe.failure("secret_unresolvable")
            _audit("admin.provider.probed", org_id,
                   {"scope": req.scope, "ok": False, "error_class": result.error_class})
            return result.to_dict()
    else:
        if req.provider is None:
            raise HTTPException(status_code=422,
                                detail="provider is required for a candidate test")
        cfg = ProviderConfig(provider=req.provider, region=req.region,
                             endpoint=req.endpoint, secret_value=req.api_key)
        model_id = req.model_id or resolve_model_id(req.provider, req.tier or "balanced")

    try:
        probe.validate_endpoint(cfg.endpoint)
    except probe.EndpointNotAllowed:
        result = probe.failure("endpoint_forbidden", tested_model=model_id)
    else:
        result = probe.run_probe(cfg, model_id)

    if req.scope is not None:
        _persist_health(org_id, req.scope, cfg.provider, result)
    _audit("admin.provider.probed", org_id,
           {"provider": cfg.provider, "scope": req.scope, "ok": result.ok,
            "error_class": result.error_class, "latency_ms": result.latency_ms})
    return result.to_dict()


@router.get("/health")
def provider_health(
    org_id: str = Depends(admin_org("/admin/models/health")),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        rows = conn.execute(
            text("select scope, provider, ok, latency_ms, error_class, checked_at "
                 "from llm_provider_health where org_id = :o order by scope"),
            {"o": org_id},
        ).mappings().all()
    return {"health": [dict(r) for r in rows]}


@router.delete("/agent-overrides/{persona}")
def clear_agent_override(
    persona: Persona,
    org_id: str = Depends(admin_org("/admin/models/agent-overrides")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        record_version(conn, org_id, persona, "delete", principal)
        conn.execute(
            text("delete from agent_llm_config where org_id = :o and agent_persona = :a"),
            {"o": org_id, "a": persona},
        )
    invalidate_secret_cache()
    _audit("admin.llm_key.cleared", org_id,
           {"scope": "agent-override", "persona": persona, "row_deleted": True})
    return {"ok": True, "persona": persona}
