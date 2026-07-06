"""Nexus Console — MCP tool-server registry & bindings (PRD-09 M1).

The sharpest security surface of the roadmap, so the controls live at the
write path: stdio transport refused outside single-user self-host (and again
at call time — defense in depth), HTTP URLs pass the SSRF egress policy
(with the MCP-specific private-network escape hatch), auth tokens are
write-only secretstore refs, and `allowed_tools = []` means DENY ALL — the
test probe's tool list turns allow-listing into a checkbox exercise.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from ...config import settings
from ...db.rls import set_org_context
from ...llm import probe
from ...runtime.mcp_backend import guard_stdio, http_list_tools, invalidate_mcp_cache
from ._guard import admin_org
from .models import _audit, _engine, _store_key

router = APIRouter(prefix="/mcp", tags=["admin", "mcp"])

Persona = Literal[
    "atlas", "bolt", "echo", "friday", "jarvis",
    "muse", "neo", "phantom", "pulse", "sentinel",
]
Phase = Literal["Initialization", "Inception", "Construction", "Operation"]
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")

# Static templates (FR-10) — prefill for the console's add form; no marketplace.
TEMPLATES = [
    {"id": "fetch", "name": "fetch", "transport": "http",
     "url": "http://localhost:8080/mcp", "allowed_tools": ["fetch"],
     "note": "Reference web-fetch server (self-hosted)."},
    {"id": "docs-search", "name": "docs-search", "transport": "http",
     "url": "https://docs.internal.example/mcp", "allowed_tools": ["search"],
     "note": "Internal documentation search — the flagship Muse binding."},
    {"id": "github", "name": "github", "transport": "http",
     "url": "https://api.githubcopilot.com/mcp/", "allowed_tools": [],
     "note": "GitHub MCP — test to list tools, then allow the ones you need."},
    {"id": "filesystem", "name": "filesystem", "transport": "stdio",
     "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
     "allowed_tools": [], "note": "stdio — single-user self-host only."},
]


class ServerIn(BaseModel):
    name: str
    transport: Literal["http", "stdio"]
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list, max_length=16)
    # WRITE-ONLY bearer token; omitted on update = keep the stored one.
    auth_token: str | None = Field(None, min_length=1)
    allowed_tools: list[str] = Field(default_factory=list, max_length=64)
    enabled: bool = True


class BindingIn(BaseModel):
    persona: Persona
    phase: Phase | None = None


def _validate_server(cfg: ServerIn) -> None:
    if not _NAME_RE.match(cfg.name):
        raise HTTPException(status_code=422,
                            detail="name must be lowercase kebab-case (2-64 chars)")
    if cfg.transport == "http":
        if not cfg.url:
            raise HTTPException(status_code=422, detail="http transport requires url")
        allow_private = (getattr(settings, "mcp_allow_private_networks", False)
                         or getattr(settings, "allow_private_llm_endpoints", False))
        try:
            probe.validate_endpoint(cfg.url, allow_private=allow_private)
        except probe.EndpointNotAllowed as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        if not cfg.command:
            raise HTTPException(status_code=422, detail="stdio transport requires command")
        try:
            guard_stdio("stdio")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    for tool in cfg.allowed_tools:
        if not tool or len(tool) > 128:
            raise HTTPException(status_code=422, detail="invalid tool name in allowlist")


def _server_out(row: dict, bindings: list[dict]) -> dict:
    return {
        "id": str(row["id"]), "name": row["name"], "transport": row["transport"],
        "url": row["url"], "command": row["command"], "args": row["args"],
        "allowed_tools": row["allowed_tools"], "enabled": row["enabled"],
        "has_auth": bool(row["auth_secret_ref"]),
        "bindings": bindings,
    }


@router.get("/templates")
def list_templates(org_id: str = Depends(admin_org("/admin/mcp"))) -> dict:
    # stdio templates are pointless (and misleading) in multi-user mode.
    multi_user = getattr(settings, "auth_required", False)
    return {"templates": [t for t in TEMPLATES
                          if t["transport"] != "stdio" or not multi_user]}


@router.get("/servers")
def list_servers(org_id: str = Depends(admin_org("/admin/mcp"))) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        rows = conn.execute(
            text("select id, name, transport, url, command, args, auth_secret_ref, "
                 "allowed_tools, enabled from mcp_servers where org_id = :o "
                 "order by name"),
            {"o": org_id},
        ).mappings().all()
        bindings = conn.execute(
            text("select server_id, persona, phase from mcp_bindings "
                 "where org_id = :o"),
            {"o": org_id},
        ).mappings().all()
    by_server: dict[str, list[dict]] = {}
    for b in bindings:
        by_server.setdefault(str(b["server_id"]), []).append(
            {"persona": b["persona"], "phase": b["phase"]})
    return {"servers": [_server_out(dict(r), by_server.get(str(r["id"]), []))
                        for r in rows]}


@router.post("/servers")
def create_server(
    cfg: ServerIn, org_id: str = Depends(admin_org("/admin/mcp"))
) -> dict:
    _validate_server(cfg)
    ref = None
    if cfg.auth_token is not None:
        ref = _store_key(cfg.auth_token, hint=f"mcp/{org_id}/{cfg.name}")
    server_id = str(uuid.uuid4())
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        dup = conn.execute(
            text("select 1 from mcp_servers where org_id = :o and name = :n"),
            {"o": org_id, "n": cfg.name},
        ).scalar()
        if dup:
            raise HTTPException(status_code=409, detail="a server with that name exists")
        conn.execute(
            text("insert into mcp_servers (id, org_id, name, transport, url, command, "
                 "args, auth_secret_ref, allowed_tools, enabled) "
                 "values (:i, :o, :n, :t, :u, :c, cast(:a as jsonb), :sr, "
                 "cast(:at as jsonb), :e)"),
            {"i": server_id, "o": org_id, "n": cfg.name, "t": cfg.transport,
             "u": cfg.url, "c": cfg.command, "a": json.dumps(cfg.args), "sr": ref,
             "at": json.dumps(cfg.allowed_tools), "e": cfg.enabled},
        )
    invalidate_mcp_cache(org_id)
    _audit("llm_config.changed", org_id,
           {"scope": "mcp", "change_kind": "update", "server": cfg.name})
    return {"ok": True, "id": server_id}


@router.put("/servers/{server_id}")
def update_server(
    server_id: str,
    cfg: ServerIn,
    org_id: str = Depends(admin_org("/admin/mcp")),
) -> dict:
    _validate_server(cfg)
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        existing = conn.execute(
            text("select auth_secret_ref from mcp_servers "
                 "where org_id = :o and id = :i"),
            {"o": org_id, "i": server_id},
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="unknown server")
        ref = existing["auth_secret_ref"]
        if cfg.auth_token is not None:
            ref = _store_key(cfg.auth_token, hint=f"mcp/{org_id}/{cfg.name}")
        conn.execute(
            text("update mcp_servers set name = :n, transport = :t, url = :u, "
                 "command = :c, args = cast(:a as jsonb), auth_secret_ref = :sr, "
                 "allowed_tools = cast(:at as jsonb), enabled = :e "
                 "where org_id = :o and id = :i"),
            {"o": org_id, "i": server_id, "n": cfg.name, "t": cfg.transport,
             "u": cfg.url, "c": cfg.command, "a": json.dumps(cfg.args), "sr": ref,
             "at": json.dumps(cfg.allowed_tools), "e": cfg.enabled},
        )
    invalidate_mcp_cache(org_id)
    _audit("llm_config.changed", org_id,
           {"scope": "mcp", "change_kind": "update", "server": cfg.name})
    return {"ok": True}


@router.delete("/servers/{server_id}")
def delete_server(
    server_id: str, org_id: str = Depends(admin_org("/admin/mcp"))
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        conn.execute(
            text("delete from mcp_servers where org_id = :o and id = :i"),
            {"o": org_id, "i": server_id},
        )
    invalidate_mcp_cache(org_id)
    _audit("llm_config.changed", org_id,
           {"scope": "mcp", "change_kind": "delete", "server_id": server_id})
    return {"ok": True}


# Injectable tools/list probe (tests swap it; the hot path never uses it).
_tool_lister = http_list_tools


def set_tool_lister(fn) -> None:
    global _tool_lister
    _tool_lister = fn


def reset_tool_lister() -> None:
    global _tool_lister
    _tool_lister = http_list_tools


@router.post("/servers/{server_id}/test")
def test_server(
    server_id: str, org_id: str = Depends(admin_org("/admin/mcp"))
) -> dict:
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        row = conn.execute(
            text("select name, transport, url, auth_secret_ref from mcp_servers "
                 "where org_id = :o and id = :i"),
            {"o": org_id, "i": server_id},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="unknown server")
    if row["transport"] != "http":
        return {"ok": False, "error": "test supports http transport only"}
    headers: dict = {}
    if row["auth_secret_ref"]:
        try:
            from ...secretstore import get_secrets

            token = get_secrets().resolve(row["auth_secret_ref"])
            if token:
                headers["Authorization"] = f"Bearer {token}"
        except Exception:
            return {"ok": False, "error": "auth secret could not be resolved"}
    t0 = time.perf_counter()
    try:
        tools = _tool_lister(row["url"], headers,
                             getattr(settings, "mcp_timeout_s", 30.0))
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}
    latency = int((time.perf_counter() - t0) * 1000)
    _audit("admin.provider.probed", org_id,
           {"scope": "mcp", "server": row["name"], "ok": True,
            "latency_ms": latency, "tools": len(tools)})
    return {"ok": True, "latency_ms": latency, "tools": tools}


@router.put("/servers/{server_id}/bindings")
def set_bindings(
    server_id: str,
    body: dict,
    org_id: str = Depends(admin_org("/admin/mcp")),
) -> dict:
    bindings = [BindingIn(**b) for b in body.get("bindings", [])]
    if len(bindings) > 64:
        raise HTTPException(status_code=422, detail="too many bindings")
    with _engine().begin() as conn:
        set_org_context(conn, org_id)
        exists = conn.execute(
            text("select 1 from mcp_servers where org_id = :o and id = :i"),
            {"o": org_id, "i": server_id},
        ).scalar()
        if not exists:
            raise HTTPException(status_code=404, detail="unknown server")
        conn.execute(
            text("delete from mcp_bindings where org_id = :o and server_id = :i"),
            {"o": org_id, "i": server_id},
        )
        for b in bindings:
            conn.execute(
                text("insert into mcp_bindings (id, org_id, server_id, persona, phase) "
                     "values (:bi, :o, :i, :p, :ph) on conflict do nothing"),
                {"bi": str(uuid.uuid4()), "o": org_id, "i": server_id,
                 "p": b.persona, "ph": b.phase},
            )
    invalidate_mcp_cache(org_id)
    _audit("llm_config.changed", org_id,
           {"scope": "mcp", "change_kind": "update", "server_id": server_id,
            "bindings": len(bindings)})
    return {"ok": True, "bindings": len(bindings)}
