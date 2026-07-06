"""Nexus Console — LLM-config history, rollback, export & import (PRD-06).

History rows store the PRIOR state (written by `models.record_version` in the
same transaction as every mutation); the state AFTER version i is version
i-1's snapshot — or the live row for the newest — so diffs are computed at
read time with no dual bookkeeping.

Export never carries secret material: `enc:` refs ARE Fernet ciphertext and
are stripped to `{"ref_kind": "encrypted"}`; `vault:`/`env:` refs export as
safe *pointers* the target instance may be able to resolve. Import reuses the
write-path validators (an import cannot smuggle in a state the PUT routes
would reject) and only writes a `secret_ref` it can actually resolve.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from ...auth.local import Identity, get_principal
from ...db.rls import set_org_context
from ._guard import admin_org
from .models import (
    _ENV_KEYED_PROVIDERS,
    FallbackEntry,
    Persona,
    Provider,
    _audit,
    _engine,
    _read_current_config,
    _validate_chain,
    _validate_provider_config,
    record_version,
)

router = APIRouter(prefix="/models", tags=["admin", "models"])

_KEYLESS_PROVIDERS = {"bedrock", "vertex", "ollama"}


# ---------------------------------------------------------------------------
# Pure helpers (hermetically unit-tested)
# ---------------------------------------------------------------------------


def _chain_summary(chain) -> list[dict] | None:
    """Redacted chain rendering for diffs: providers + key presence only."""
    if chain is None:
        return None
    return [{"provider": e.get("provider"), "has_key": bool(e.get("secret_ref"))}
            for e in chain]


def config_diff(before: dict | None, after: dict | None) -> list[dict]:
    """Field-level diff between two snapshots. secret_ref never renders as a
    value — only set/changed/cleared."""
    out: list[dict] = []
    for field in sorted(set(before or {}) | set(after or {})):
        b = (before or {}).get(field)
        a = (after or {}).get(field)
        if b == a:
            continue
        if field == "secret_ref":
            out.append({"field": "secret",
                        "from": "set" if b else "unset",
                        "to": "changed" if (b and a) else ("set" if a else "cleared")})
        elif field == "failover_chain":
            out.append({"field": field,
                        "from": _chain_summary(b), "to": _chain_summary(a)})
        else:
            out.append({"field": field, "from": b, "to": a})
    return out


def secret_export(ref: str | None, provider: str) -> dict:
    """The §5.3 transform table — never the raw ref for `enc:` (the ref IS the
    ciphertext); pointers only for vault/env."""
    required = provider not in _KEYLESS_PROVIDERS
    if not ref:
        return {"required": required}
    if ref.startswith("enc:"):
        return {"required": True, "ref_kind": "encrypted"}
    if ref.startswith("vault:"):
        return {"required": True, "ref_kind": "vault", "ref_hint": ref}
    if ref.startswith("env:"):
        return {"required": True, "ref_kind": "env", "ref_hint": ref}
    return {"required": True, "ref_kind": "unknown"}


def _secret_resolvable(ref: str | None) -> bool:
    if not ref:
        return False
    try:
        from ...secretstore import get_secrets

        return get_secrets().resolve(ref) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Versions + rollback
# ---------------------------------------------------------------------------


@router.get("/versions")
def list_versions(
    scope: str | None = None,
    limit: int = 20,
    org_id: str = Depends(admin_org("/admin/models/versions")),
) -> dict:
    limit = max(1, min(limit, 100))
    where = "org_id = :o" + (" and scope = :s" if scope else "")
    params: dict = {"o": org_id, "lim": limit}
    if scope:
        params["s"] = scope
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        rows = conn.execute(
            text(f"select id, scope, change_kind, snapshot, actor_label, created_at "
                 f"from llm_config_versions where {where} "
                 f"order by created_at desc, id desc limit :lim"),
            params,
        ).mappings().all()
        # after-state per scope: newest version's after = live row; older
        # versions' after = the next-newer version's snapshot (same scope).
        live: dict[str, dict | None] = {}
        for r in rows:
            if r["scope"] not in live:
                live[r["scope"]] = _read_current_config(conn, org_id, r["scope"])
    newer_snapshot_by_scope: dict[str, dict | None] = {}
    versions = []
    for r in rows:  # newest → oldest
        s = r["scope"]
        after = newer_snapshot_by_scope.get(s, live.get(s))
        versions.append({
            "id": str(r["id"]), "scope": s, "change_kind": r["change_kind"],
            "actor_label": r["actor_label"], "created_at": r["created_at"],
            "diff": config_diff(r["snapshot"], after),
        })
        newer_snapshot_by_scope[s] = r["snapshot"]
    return {"versions": versions}


@router.post("/versions/{version_id}/rollback")
def rollback_version(
    version_id: str,
    org_id: str = Depends(admin_org("/admin/models/versions")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        v = conn.execute(
            text("select scope, snapshot from llm_config_versions "
                 "where org_id = :o and id = :i"),
            {"o": org_id, "i": version_id},
        ).mappings().first()
        if not v:
            raise HTTPException(status_code=404, detail="unknown version")
        scope, snap = v["scope"], v["snapshot"]

        requires_reentry = False
        if snap is not None:
            # A snapshot may predate current rules — validate through them
            # rather than blind-writing (e.g. an endpoint now failing SSRF).
            _validate_provider_config(snap["provider"], snap.get("endpoint"),
                                      tier_map=snap.get("tier_map"))
            if scope == "org":
                _validate_chain([FallbackEntry(**{k: e.get(k) for k in
                                                  ("provider", "region", "endpoint", "tier_map")})
                                 for e in (snap.get("failover_chain") or [])])
            # FR-5: only restore secret_refs that still resolve.
            if snap.get("secret_ref") and not _secret_resolvable(snap["secret_ref"]):
                snap = {**snap, "secret_ref": None}
                requires_reentry = True
            if scope == "org" and snap.get("failover_chain"):
                chain = []
                for e in snap["failover_chain"]:
                    if e.get("secret_ref") and not _secret_resolvable(e["secret_ref"]):
                        e = {**e, "secret_ref": None}
                        requires_reentry = True
                    chain.append(e)
                snap = {**snap, "failover_chain": chain}

        record_version(conn, org_id, scope, "rollback", principal)
        if snap is None:
            if scope == "org":
                conn.execute(text("delete from org_llm_config where org_id = :o"),
                             {"o": org_id})
            else:
                conn.execute(text("delete from agent_llm_config "
                                  "where org_id = :o and agent_persona = :p"),
                             {"o": org_id, "p": scope})
        elif scope == "org":
            conn.execute(
                text("insert into org_llm_config "
                     "(org_id, provider, region, endpoint, tier_map, secret_ref, "
                     "failover_chain, pricing_override) "
                     "values (:o, :p, :r, :e, cast(:t as jsonb), :sr, "
                     "cast(:fc as jsonb), cast(:po as jsonb)) "
                     "on conflict (org_id) do update set provider = excluded.provider, "
                     "region = excluded.region, endpoint = excluded.endpoint, "
                     "tier_map = excluded.tier_map, secret_ref = excluded.secret_ref, "
                     "failover_chain = excluded.failover_chain, "
                     "pricing_override = excluded.pricing_override"),
                {"o": org_id, "p": snap["provider"], "r": snap.get("region"),
                 "e": snap.get("endpoint"), "t": json.dumps(snap.get("tier_map")),
                 "sr": snap.get("secret_ref"),
                 "fc": json.dumps(snap.get("failover_chain") or []),
                 "po": json.dumps(snap.get("pricing_override"))
                       if snap.get("pricing_override") is not None else None},
            )
        else:
            conn.execute(
                text("insert into agent_llm_config "
                     "(org_id, agent_persona, provider, model_id, region, endpoint, secret_ref) "
                     "values (:o, :a, :p, :m, :r, :e, :sr) "
                     "on conflict (org_id, agent_persona) do update set "
                     "provider = excluded.provider, model_id = excluded.model_id, "
                     "region = excluded.region, endpoint = excluded.endpoint, "
                     "secret_ref = excluded.secret_ref"),
                {"o": org_id, "a": scope, "p": snap["provider"],
                 "m": snap.get("model_id"), "r": snap.get("region"),
                 "e": snap.get("endpoint"), "sr": snap.get("secret_ref")},
            )
    from ...llm.factory import invalidate_secret_cache

    invalidate_secret_cache()
    _audit("llm_config.rolled_back", org_id,
           {"scope": scope, "version_id": version_id,
            "secret_requires_reentry": requires_reentry})
    return {"ok": True, "restored_scope": scope,
            "secret_requires_reentry": requires_reentry}


# ---------------------------------------------------------------------------
# Export / import
# ---------------------------------------------------------------------------


@router.get("/export")
def export_models(
    org_id: str = Depends(admin_org("/admin/models/export")),
) -> Response:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        org = _read_current_config(conn, org_id, "org")
        agents = conn.execute(
            text("select agent_persona, provider, model_id, region, endpoint, secret_ref "
                 "from agent_llm_config where org_id = :o order by agent_persona"),
            {"o": org_id},
        ).mappings().all()
    from ...llm.presets import load_catalog

    doc: dict = {
        "format_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "catalog_version": load_catalog().catalog_version,
        "org_default": None,
        "agent_overrides": [],
    }
    if org:
        doc["org_default"] = {
            "provider": org["provider"], "region": org.get("region"),
            "endpoint": org.get("endpoint"), "tier_map": org.get("tier_map"),
            "secret": secret_export(org.get("secret_ref"), org["provider"]),
            "pricing_override": org.get("pricing_override"),
            "failover_chain": [
                {"provider": e.get("provider"), "region": e.get("region"),
                 "endpoint": e.get("endpoint"), "tier_map": e.get("tier_map"),
                 "secret": secret_export(e.get("secret_ref"), e.get("provider", ""))}
                for e in (org.get("failover_chain") or [])
            ],
        }
    for a in agents:
        doc["agent_overrides"].append({
            "agent_persona": a["agent_persona"], "provider": a["provider"],
            "model_id": a["model_id"], "region": a["region"], "endpoint": a["endpoint"],
            "secret": secret_export(a["secret_ref"], a["provider"]),
        })
    _audit("llm_config.exported", org_id,
           {"agent_overrides": len(doc["agent_overrides"]),
            "has_org_default": doc["org_default"] is not None})
    return Response(
        content=json.dumps(doc, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="pdlcflow-models-export.json"'},
    )


class ImportSecret(BaseModel):
    model_config = ConfigDict(extra="ignore")
    required: bool = False
    ref_kind: str | None = None
    ref_hint: str | None = None


class ImportChainEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    provider: Provider
    region: str | None = None
    endpoint: str | None = None
    tier_map: dict[str, str] | None = None
    secret: ImportSecret | None = None


class ImportOrgDefault(BaseModel):
    model_config = ConfigDict(extra="ignore")
    provider: Provider
    tier_map: dict[str, str]
    region: str | None = None
    endpoint: str | None = None
    failover_chain: list[ImportChainEntry] = Field(default_factory=list, max_length=3)
    secret: ImportSecret | None = None
    pricing_override: dict[str, dict[str, float]] | None = None


class ImportOverride(BaseModel):
    model_config = ConfigDict(extra="ignore")
    agent_persona: Persona
    provider: Provider
    model_id: str
    region: str | None = None
    endpoint: str | None = None
    secret: ImportSecret | None = None


class ImportDoc(BaseModel):
    model_config = ConfigDict(extra="ignore")
    format_version: int = 1
    org_default: ImportOrgDefault | None = None
    agent_overrides: list[ImportOverride] = Field(default_factory=list)


def _plan_secret(secret: ImportSecret | None, provider: str) -> tuple[str, str | None]:
    """→ (plan label, reusable secret_ref or None)."""
    if provider in _KEYLESS_PROVIDERS:
        return "none", None
    hint = secret.ref_hint if secret else None
    if hint and _secret_resolvable(hint):
        return "reusable", hint
    if (secret and secret.required) or provider in _ENV_KEYED_PROVIDERS:
        return "re-entry required", None
    return "none", None


def _plan_import(doc: ImportDoc, org_id: str) -> list[dict]:
    plan: list[dict] = []

    def _item(scope: str, provider: str, endpoint, tier_map, secret,
              *, chain: list[ImportChainEntry] | None = None) -> dict:
        reasons: list[str] = []
        try:
            _validate_provider_config(provider, endpoint, tier_map=tier_map)
            if chain is not None:
                _validate_chain([FallbackEntry(provider=e.provider, region=e.region,
                                               endpoint=e.endpoint, tier_map=e.tier_map)
                                 for e in chain])
        except HTTPException as exc:
            reasons.append(str(exc.detail))
        secret_plan, _ = _plan_secret(secret, provider)
        if chain:
            for i, e in enumerate(chain):
                _s_plan, s_ref = _plan_secret(e.secret, e.provider)
                if e.provider in _ENV_KEYED_PROVIDERS and s_ref is None:
                    reasons.append(
                        f"failover_chain[{i}]: {e.provider} needs a key the target "
                        "cannot resolve — remove the entry or use a shared vault ref")
        return {"scope": scope, "action": "error" if reasons else "pending",
                "reasons": reasons, "secret": secret_plan}

    if doc.org_default is not None:
        d = doc.org_default
        plan.append(_item("org", d.provider, d.endpoint, d.tier_map, d.secret,
                          chain=d.failover_chain))
    for o in doc.agent_overrides:
        plan.append(_item(o.agent_persona, o.provider, o.endpoint, None, o.secret))

    # Classify pending items as create/overwrite against the live rows.
    if any(p["action"] == "pending" for p in plan):
        with _engine().begin() as conn:
            set_org_context(conn, org_id)
            for p in plan:
                if p["action"] != "pending":
                    continue
                p["action"] = ("overwrite"
                               if _read_current_config(conn, org_id, p["scope"])
                               else "create")
    return plan


@router.post("/import")
def import_models(
    doc: ImportDoc,
    dry_run: bool = False,
    strategy: Literal["merge", "replace"] = "merge",
    org_id: str = Depends(admin_org("/admin/models/import")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    if doc.format_version != 1:
        raise HTTPException(status_code=422, detail="unsupported format_version")
    plan = _plan_import(doc, org_id)
    if dry_run:
        return {"plan": plan, "strategy": strategy}
    if any(p["action"] == "error" for p in plan):
        raise HTTPException(status_code=422, detail={"plan": plan})

    version_ids = 0
    with _engine().begin() as conn:  # all-or-nothing (FR-7)
        set_org_context(conn, org_id)
        if doc.org_default is not None:
            d = doc.org_default
            _, org_ref = _plan_secret(d.secret, d.provider)
            chain = []
            for e in d.failover_chain:
                _, e_ref = _plan_secret(e.secret, e.provider)
                chain.append({"provider": e.provider, "region": e.region,
                              "endpoint": e.endpoint, "tier_map": e.tier_map,
                              "secret_ref": e_ref})
            record_version(conn, org_id, "org", "import", principal)
            version_ids += 1
            conn.execute(
                text("insert into org_llm_config "
                     "(org_id, provider, region, endpoint, tier_map, secret_ref, "
                     "failover_chain, pricing_override) "
                     "values (:o, :p, :r, :e, cast(:t as jsonb), :sr, "
                     "cast(:fc as jsonb), cast(:po as jsonb)) "
                     "on conflict (org_id) do update set provider = excluded.provider, "
                     "region = excluded.region, endpoint = excluded.endpoint, "
                     "tier_map = excluded.tier_map, secret_ref = excluded.secret_ref, "
                     "failover_chain = excluded.failover_chain, "
                     "pricing_override = excluded.pricing_override"),
                {"o": org_id, "p": d.provider, "r": d.region, "e": d.endpoint,
                 "t": json.dumps(d.tier_map), "sr": org_ref, "fc": json.dumps(chain),
                 "po": json.dumps(d.pricing_override)
                       if d.pricing_override is not None else None},
            )
        elif strategy == "replace":
            if _read_current_config(conn, org_id, "org") is not None:
                record_version(conn, org_id, "org", "import", principal)
                version_ids += 1
                conn.execute(text("delete from org_llm_config where org_id = :o"),
                             {"o": org_id})

        doc_personas = {o.agent_persona for o in doc.agent_overrides}
        for o in doc.agent_overrides:
            _, ref = _plan_secret(o.secret, o.provider)
            record_version(conn, org_id, o.agent_persona, "import", principal)
            version_ids += 1
            conn.execute(
                text("insert into agent_llm_config "
                     "(org_id, agent_persona, provider, model_id, region, endpoint, secret_ref) "
                     "values (:o, :a, :p, :m, :r, :e, :sr) "
                     "on conflict (org_id, agent_persona) do update set "
                     "provider = excluded.provider, model_id = excluded.model_id, "
                     "region = excluded.region, endpoint = excluded.endpoint, "
                     "secret_ref = excluded.secret_ref"),
                {"o": org_id, "a": o.agent_persona, "p": o.provider, "m": o.model_id,
                 "r": o.region, "e": o.endpoint, "sr": ref},
            )
        if strategy == "replace":
            existing = conn.execute(
                text("select agent_persona from agent_llm_config where org_id = :o"),
                {"o": org_id},
            ).scalars().all()
            for persona in set(existing) - doc_personas:
                record_version(conn, org_id, persona, "import", principal)
                version_ids += 1
                conn.execute(
                    text("delete from agent_llm_config "
                         "where org_id = :o and agent_persona = :a"),
                    {"o": org_id, "a": persona},
                )
    from ...llm.factory import invalidate_secret_cache

    invalidate_secret_cache()
    _audit("llm_config.imported", org_id,
           {"strategy": strategy, "applied": version_ids})
    return {"ok": True, "applied": version_ids, "plan": plan}
