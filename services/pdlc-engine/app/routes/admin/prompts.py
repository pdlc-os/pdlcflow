"""Nexus Console — persona prompt overrides & packs (PRD-10).

Versions are immutable: creating is POST-only (draft), activation flips
status (archiving the prior active), deactivation returns the persona to the
packaged soul-spec. Packs export active overrides as plain text — no secrets,
no org identifiers — and always import as DRAFTS (never auto-activated:
cc-switch's "backfill protection" translated).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from ...auth.local import Identity, get_principal
from ...db.rls import set_org_context
from ...runtime.prompt_backend import invalidate_prompt_cache
from ._guard import admin_org
from .models import _audit, _engine

router = APIRouter(prefix="/prompts", tags=["admin", "prompts"])

# The 9 LLM personas — sentinel is a deterministic evaluator, not an LLM.
PROMPT_PERSONAS: tuple[str, ...] = (
    "atlas", "bolt", "echo", "friday", "jarvis", "muse", "neo", "phantom", "pulse",
)
Persona = Literal[
    "atlas", "bolt", "echo", "friday", "jarvis", "muse", "neo", "phantom", "pulse",
]
_MAX_BODY = 32 * 1024  # bounds token cost + context blowout


def validate_prompt_body(body: str) -> None:
    """DB-free guardrails: size cap; if frontmatter declares a tier it must be
    a real one (typos would silently mean 'premium'). NOTE: frontmatter tier in
    ORG prompts is otherwise IGNORED — model tier stays in agent_llm_config."""
    if not body or not body.strip():
        raise HTTPException(status_code=422, detail="prompt body is empty")
    if len(body.encode()) > _MAX_BODY:
        raise HTTPException(status_code=422, detail="prompt body exceeds 32 KiB")
    lines = body.splitlines()
    if lines and lines[0].strip() == "---":
        from pdlc_graph.personas import TIERS

        for line in lines[1:]:
            if line.strip() == "---":
                break
            if line.strip().startswith("tier:"):
                tier = line.split(":", 1)[1].strip()
                if tier not in TIERS:
                    raise HTTPException(
                        status_code=422,
                        detail=f"frontmatter tier {tier!r} is not one of {TIERS} "
                               "(note: tier in org prompts is informational only)")


class DraftBody(BaseModel):
    body: str


@router.get("")
def list_prompts(org_id: str = Depends(admin_org("/admin/prompts"))) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        rows = conn.execute(
            text("select persona, count(*) as versions, "
                 "max(version) filter (where status = 'active') as active_version "
                 "from persona_prompts where org_id = :o group by persona"),
            {"o": org_id},
        ).mappings().all()
    by_persona = {r["persona"]: r for r in rows}
    return {"personas": [
        {"persona": p,
         "versions": by_persona[p]["versions"] if p in by_persona else 0,
         "active_version": by_persona[p]["active_version"] if p in by_persona else None,
         "overridden": bool(p in by_persona and by_persona[p]["active_version"])}
        for p in PROMPT_PERSONAS
    ]}


@router.get("/export")
def export_pack(org_id: str = Depends(admin_org("/admin/prompts"))) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        rows = conn.execute(
            text("select persona, version, body from persona_prompts "
                 "where org_id = :o and status = 'active' order by persona"),
            {"o": org_id},
        ).mappings().all()
    _audit("prompt_pack.exported", org_id, {"personas": len(rows)})
    return {
        "format": "pdlcflow.prompt-pack/v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "prompts": {r["persona"]: {"body": r["body"], "source_version": r["version"]}
                    for r in rows},
    }


class PackDoc(BaseModel):
    format: str
    prompts: dict[str, dict]


@router.post("/import")
def import_pack(
    pack: PackDoc,
    dry_run: bool = False,
    org_id: str = Depends(admin_org("/admin/prompts")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    """Imports land as DRAFTS — review + activate explicitly per persona."""
    if pack.format != "pdlcflow.prompt-pack/v1":
        raise HTTPException(status_code=422, detail="unsupported pack format")
    results: dict[str, str] = {}
    valid: dict[str, str] = {}
    for persona, entry in pack.prompts.items():
        if persona not in PROMPT_PERSONAS:
            results[persona] = "error: unknown persona (sentinel is not overridable)"
            continue
        body = entry.get("body") if isinstance(entry, dict) else None
        try:
            validate_prompt_body(body or "")
        except HTTPException as exc:
            results[persona] = f"error: {exc.detail}"
            continue
        results[persona] = "draft"
        valid[persona] = body  # type: ignore[assignment]
    if dry_run:
        return {"plan": results}
    if any(v.startswith("error") for v in results.values()):
        raise HTTPException(status_code=422, detail={"plan": results})
    created: dict[str, int] = {}
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        for persona, body in valid.items():
            created[persona] = _insert_draft(conn, org_id, persona, body, principal)
    _audit("prompt_pack.imported", org_id, {"personas": list(created)})
    return {"ok": True, "created": created}


@router.get("/{persona}")
def get_persona_prompts(
    persona: Persona,
    org_id: str = Depends(admin_org("/admin/prompts")),
) -> dict:
    from pdlc_graph.personas import load_persona_spec

    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        rows = conn.execute(
            text("select version, status, created_at, activated_at "
                 "from persona_prompts where org_id = :o and persona = :p "
                 "order by version desc"),
            {"o": org_id, "p": persona},
        ).mappings().all()
    return {
        "persona": persona,
        "packaged_default": load_persona_spec(persona),
        "versions": [dict(r) for r in rows],
    }


@router.get("/{persona}/versions/{version}")
def get_prompt_version(
    persona: Persona,
    version: int,
    org_id: str = Depends(admin_org("/admin/prompts")),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        row = conn.execute(
            text("select version, status, body from persona_prompts "
                 "where org_id = :o and persona = :p and version = :v"),
            {"o": org_id, "p": persona, "v": version},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="unknown version")
    return dict(row)


def _insert_draft(conn, org_id: str, persona: str, body: str,
                  principal: Identity | None) -> int:
    next_v = conn.execute(
        text("select coalesce(max(version), 0) + 1 from persona_prompts "
             "where org_id = :o and persona = :p"),
        {"o": org_id, "p": persona},
    ).scalar()
    created_by = None
    if principal is not None:
        try:
            created_by = str(uuid.UUID(str(principal.user_id)))
        except (ValueError, TypeError):
            created_by = None
    conn.execute(
        text("insert into persona_prompts "
             "(id, org_id, persona, version, body, status, created_by) "
             "values (:i, :o, :p, :v, :b, 'draft', :u)"),
        {"i": str(uuid.uuid4()), "o": org_id, "p": persona, "v": next_v,
         "b": body, "u": created_by},
    )
    return int(next_v)


@router.post("/{persona}")
def create_draft(
    persona: Persona,
    draft: DraftBody,
    org_id: str = Depends(admin_org("/admin/prompts")),
    principal: Identity | None = Depends(get_principal),
) -> dict:
    validate_prompt_body(draft.body)
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        version = _insert_draft(conn, org_id, persona, draft.body, principal)
    return {"ok": True, "persona": persona, "version": version}


@router.post("/{persona}/versions/{version}/activate")
def activate_version(
    persona: Persona,
    version: int,
    org_id: str = Depends(admin_org("/admin/prompts")),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        exists = conn.execute(
            text("select status from persona_prompts "
                 "where org_id = :o and persona = :p and version = :v"),
            {"o": org_id, "p": persona, "v": version},
        ).scalar()
        if exists is None:
            raise HTTPException(status_code=404, detail="unknown version")
        conn.execute(
            text("update persona_prompts set status = 'archived' "
                 "where org_id = :o and persona = :p and status = 'active'"),
            {"o": org_id, "p": persona},
        )
        conn.execute(
            text("update persona_prompts set status = 'active', activated_at = now() "
                 "where org_id = :o and persona = :p and version = :v"),
            {"o": org_id, "p": persona, "v": version},
        )
    invalidate_prompt_cache(org_id)
    _audit("prompt.activated", org_id, {"persona": persona, "version": version})
    return {"ok": True, "persona": persona, "active_version": version}


@router.post("/{persona}/deactivate")
def deactivate(
    persona: Persona,
    org_id: str = Depends(admin_org("/admin/prompts")),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        conn.execute(
            text("update persona_prompts set status = 'archived' "
                 "where org_id = :o and persona = :p and status = 'active'"),
            {"o": org_id, "p": persona},
        )
    invalidate_prompt_cache(org_id)
    _audit("prompt.deactivated", org_id, {"persona": persona})
    return {"ok": True, "persona": persona}
