"""Atlas Console Models settings — org default + 10 per-agent overrides + test."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/models", tags=["admin", "models"])

Provider = Literal["bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama"]
Persona = Literal[
    "atlas", "bolt", "echo", "friday", "jarvis",
    "muse", "neo", "phantom", "pulse", "sentinel",
]


class OrgDefault(BaseModel):
    provider: Provider
    tier_map: dict[str, str]  # {"opus": "...", "sonnet": "...", "haiku": "..."}
    region: str | None = None
    endpoint: str | None = None


class AgentOverride(BaseModel):
    agent_persona: Persona
    provider: Provider
    model_id: str
    region: str | None = None
    endpoint: str | None = None


@router.get("/org-default", response_model=OrgDefault | None)
def get_org_default() -> OrgDefault | None:
    return None  # Phase A stub


@router.put("/org-default")
def set_org_default(_cfg: OrgDefault) -> dict:
    return {"ok": True}  # Phase A stub


@router.get("/agent-overrides", response_model=list[AgentOverride])
def list_agent_overrides() -> list[AgentOverride]:
    return []


@router.put("/agent-overrides/{persona}")
def set_agent_override(persona: Persona, _cfg: AgentOverride) -> dict:
    return {"ok": True, "persona": persona}


@router.post("/test")
def test_connection(provider: Provider) -> dict:
    return {"provider": provider, "ok": True, "phase": "A stub"}
