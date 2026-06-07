"""Nexus Console — Models settings: org default + per-agent overrides.

Persists to org_llm_config / agent_llm_config (RLS-FORCEd, scoped to the admin's
org). The LLM factory reads these so per-tenant / per-agent model selection takes
effect. Tiers are provider-neutral (premium / balanced / economy); the factory's
tier_map turns a tier into a concrete model for the chosen provider.
"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from ...config import settings
from ...db.rls import set_org_context
from ...db.session import get_sync_engine
from ._guard import admin_org

router = APIRouter(prefix="/models", tags=["admin", "models"])

Provider = Literal["bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama"]
Persona = Literal[
    "atlas", "bolt", "echo", "friday", "jarvis",
    "muse", "neo", "phantom", "pulse", "sentinel",
]


class OrgDefault(BaseModel):
    provider: Provider
    tier_map: dict[str, str]  # {"premium": "...", "balanced": "...", "economy": "..."}
    region: str | None = None
    endpoint: str | None = None


class AgentOverride(BaseModel):
    agent_persona: Persona
    provider: Provider
    model_id: str
    region: str | None = None
    endpoint: str | None = None


def _engine():
    return get_sync_engine(settings)


@router.get("/org-default", response_model=OrgDefault | None)
def get_org_default(
    org_id: str = Depends(admin_org("/admin/models/org-default")),
) -> OrgDefault | None:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        row = conn.execute(
            text("select provider, tier_map, region, endpoint from org_llm_config where org_id = :o"),
            {"o": org_id},
        ).mappings().first()
    return OrgDefault(**row) if row else None


@router.put("/org-default")
def set_org_default(
    cfg: OrgDefault, org_id: str = Depends(admin_org("/admin/models/org-default"))
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        conn.execute(
            text(
                "insert into org_llm_config (org_id, provider, region, endpoint, tier_map) "
                "values (:o, :p, :r, :e, cast(:t as jsonb)) "
                "on conflict (org_id) do update set "
                "provider = excluded.provider, region = excluded.region, "
                "endpoint = excluded.endpoint, tier_map = excluded.tier_map"
            ),
            {"o": org_id, "p": cfg.provider, "r": cfg.region, "e": cfg.endpoint,
             "t": json.dumps(cfg.tier_map)},
        )
    return {"ok": True}


@router.get("/agent-overrides", response_model=list[AgentOverride])
def list_agent_overrides(
    org_id: str = Depends(admin_org("/admin/models/agent-overrides")),
) -> list[AgentOverride]:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        rows = conn.execute(
            text("select agent_persona, provider, model_id, region, endpoint "
                 "from agent_llm_config where org_id = :o order by agent_persona"),
            {"o": org_id},
        ).mappings().all()
    return [AgentOverride(**r) for r in rows]


@router.put("/agent-overrides/{persona}")
def set_agent_override(
    persona: Persona,
    cfg: AgentOverride,
    org_id: str = Depends(admin_org("/admin/models/agent-overrides")),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        conn.execute(
            text(
                "insert into agent_llm_config "
                "(org_id, agent_persona, provider, model_id, region, endpoint) "
                "values (:o, :a, :p, :m, :r, :e) "
                "on conflict (org_id, agent_persona) do update set "
                "provider = excluded.provider, model_id = excluded.model_id, "
                "region = excluded.region, endpoint = excluded.endpoint"
            ),
            {"o": org_id, "a": persona, "p": cfg.provider, "m": cfg.model_id,
             "r": cfg.region, "e": cfg.endpoint},
        )
    return {"ok": True, "persona": persona}


@router.delete("/agent-overrides/{persona}")
def clear_agent_override(
    persona: Persona,
    org_id: str = Depends(admin_org("/admin/models/agent-overrides")),
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        conn.execute(
            text("delete from agent_llm_config where org_id = :o and agent_persona = :a"),
            {"o": org_id, "a": persona},
        )
    return {"ok": True, "persona": persona}
