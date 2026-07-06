"""MCP tool backend (PRD-09) — implements pdlc_graph's tool port.

Per call: resolve the turn's org (`current_org`), load the enabled servers
bound to (persona, phase), enforce the allowlist and the stdio guard, resolve
the bearer token from the secretstore, execute `tools/call` over Streamable
HTTP with a hard timeout + result-size cap + per-turn call cap, emit a
`tool.called` clickstream event and a `pdlc.tool.<name>` span nested under the
node span, and RETURN a dict — a tool failure never raises into a node.

`list_tools` is deliberately network-free: the tool list IS the server's
`allowed_tools` allowlist (the admin test probe is where live `tools/list`
happens). The `mcp` SDK is an ENGINE dependency, imported lazily inside the
client functions — the graph package and hermetic CI never touch it.
"""

from __future__ import annotations

import logging
import time
import uuid as _uuid

from sqlalchemy import text

from ..config import settings

log = logging.getLogger("pdlc.runtime.mcp")

_BINDINGS_TTL_S = 30.0
_NEGATIVE_TTL_S = 60.0  # dead server → don't retry on every node

_bindings_cache: dict[tuple[str, str, str], tuple[list[dict], float]] = {}
_negative_cache: dict[tuple[str, str], float] = {}
_turn_calls: dict[str, int] = {}


def reset_mcp_caches() -> None:
    _bindings_cache.clear()
    _negative_cache.clear()
    _turn_calls.clear()


def invalidate_mcp_cache(org_id: str | None = None) -> None:
    if org_id is None:
        _bindings_cache.clear()
    else:
        for k in [k for k in _bindings_cache if k[0] == org_id]:
            _bindings_cache.pop(k, None)


def guard_stdio(transport: str) -> None:
    """stdio MCP servers execute commands on the engine host — single-user
    self-host only, exactly like CLI providers (_guard_cli)."""
    if transport != "stdio":
        return
    if not getattr(settings, "enable_stdio_mcp", False):
        raise ValueError(
            "stdio MCP servers require PDLC_ENABLE_STDIO_MCP=true "
            "(single-user self-host only).")
    if getattr(settings, "auth_required", False):
        raise ValueError(
            "stdio MCP servers are not allowed in multi-user/SaaS mode "
            "(PDLC_AUTH_REQUIRED is on) — they execute commands on the engine host.")


# ---------------------------------------------------------------------------
# Live MCP client (lazy `mcp` SDK; injectable for tests)
# ---------------------------------------------------------------------------


def _run_async(coro, timeout_s: float):
    import asyncio

    return asyncio.run(asyncio.wait_for(coro, timeout_s + 5))


def _http_call_tool(url: str, headers: dict, tool: str, arguments: dict,
                    timeout_s: float) -> str:
    async def _go():
        import asyncio

        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(url, headers=headers or None) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                result = await asyncio.wait_for(
                    session.call_tool(tool, arguments), timeout_s)
                return "\n".join(
                    c.text for c in result.content if getattr(c, "text", None))

    return _run_async(_go(), timeout_s)


def http_list_tools(url: str, headers: dict, timeout_s: float) -> list[dict]:
    """Live tools/list — used by the admin test endpoint, not the hot path."""
    async def _go():
        import asyncio

        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(url, headers=headers or None) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                listing = await asyncio.wait_for(session.list_tools(), timeout_s)
                return [{"name": t.name, "description": t.description or ""}
                        for t in listing.tools]

    return _run_async(_go(), timeout_s)


_call_client = _http_call_tool


def set_call_client(fn) -> None:
    """Tests inject a fake (url, headers, tool, arguments, timeout_s) -> str."""
    global _call_client
    _call_client = fn


def reset_call_client() -> None:
    global _call_client
    _call_client = _http_call_tool


# ---------------------------------------------------------------------------
# The backend
# ---------------------------------------------------------------------------


class MCPToolBackend:
    def __init__(self, db) -> None:
        self._db = db

    # -- org / binding resolution --------------------------------------------
    @staticmethod
    def _org(persona: str) -> str | None:
        from pdlc_graph.ports import current_org

        org = current_org()
        try:
            _uuid.UUID(str(org))
            return str(org)
        except (ValueError, TypeError):
            return None

    def _bound_servers(self, org: str, persona: str, phase: str | None) -> list[dict]:
        key = (org, persona, phase or "")
        hit = _bindings_cache.get(key)
        if hit is not None and hit[1] > time.monotonic():
            return hit[0]
        from ..db.rls import set_org_context

        try:
            with self._db.begin() as conn:
                set_org_context(conn, org)
                rows = conn.execute(
                    text("select distinct s.id, s.name, s.transport, s.url, s.command, "
                         "s.auth_secret_ref, s.allowed_tools "
                         "from mcp_servers s join mcp_bindings b on b.server_id = s.id "
                         "where s.org_id = :o and s.enabled and b.persona = :p "
                         "and (b.phase is null or b.phase = :ph)"),
                    {"o": org, "p": persona, "ph": phase or ""},
                ).mappings().all()
            servers = [dict(r) for r in rows]
        except Exception:
            servers = []
        _bindings_cache[key] = (servers, time.monotonic() + _BINDINGS_TTL_S)
        return servers

    # -- port implementation ---------------------------------------------------
    def list_tools(self, persona: str, *, phase: str | None = None) -> list[dict]:
        org = self._org(persona)
        if org is None:
            return []
        return [
            {"server": s["name"], "tool": t}
            for s in self._bound_servers(org, persona, phase)
            for t in (s["allowed_tools"] or [])
        ]

    def call_tool(self, persona: str, server: str, tool: str, arguments: dict,
                  *, phase: str | None = None) -> dict:
        org = self._org(persona)
        if org is None:
            return {"ok": False, "error": "no org context", "content": None}
        row = next((s for s in self._bound_servers(org, persona, phase)
                    if s["name"] == server), None)
        if row is None:
            return {"ok": False, "error": f"server {server!r} not bound for {persona}",
                    "content": None}
        if tool not in (row["allowed_tools"] or []):
            return {"ok": False, "error": f"tool {tool!r} not in the allowlist",
                    "content": None}
        try:
            guard_stdio(row["transport"])  # defense in depth (config may predate a mode flip)
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "content": None}
        if row["transport"] != "http":
            return {"ok": False, "error": "stdio execution not implemented in v1",
                    "content": None}

        # Per-turn call cap.
        from pdlc_graph.llm_port import current_thread

        thread = current_thread()
        cap = getattr(settings, "mcp_calls_per_turn", 20)
        if thread:
            if len(_turn_calls) > 1000:
                _turn_calls.clear()
            n = _turn_calls.get(thread, 0) + 1
            _turn_calls[thread] = n
            if n > cap:
                return {"ok": False,
                        "error": f"per-turn tool-call cap reached ({cap})",
                        "content": None}

        neg_key = (org, row["name"])
        neg = _negative_cache.get(neg_key)
        if neg is not None and neg > time.monotonic():
            return {"ok": False, "error": "server recently failed (cooling down)",
                    "content": None}

        headers: dict = {}
        if row["auth_secret_ref"]:
            try:
                from ..secretstore import get_secrets

                token = get_secrets().resolve(row["auth_secret_ref"])
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except Exception:
                return {"ok": False, "error": "auth secret could not be resolved",
                        "content": None}

        timeout_s = getattr(settings, "mcp_timeout_s", 30.0)
        max_bytes = getattr(settings, "mcp_max_result_bytes", 64 * 1024)
        t0 = time.perf_counter()
        from pdlc_graph import tracing

        with tracing.span(f"pdlc.tool.{tool}", kind="client",
                          attributes={"pdlc.tool.server": row["name"],
                                      "pdlc.agent_persona": persona}) as span:
            try:
                content = _call_client(row["url"], headers, tool, arguments, timeout_s)
            except Exception as exc:
                _negative_cache[neg_key] = time.monotonic() + _NEGATIVE_TTL_S
                duration_ms = int((time.perf_counter() - t0) * 1000)
                span.record_exception(exc)
                _emit_tool_event(org, persona, row["name"], tool, duration_ms,
                                 ok=False, size=0)
                return {"ok": False, "error": type(exc).__name__, "content": None,
                        "duration_ms": duration_ms}
        _negative_cache.pop(neg_key, None)
        truncated = False
        if content and len(content.encode()) > max_bytes:
            content = content.encode()[:max_bytes].decode(errors="ignore") + "\n[truncated]"
            truncated = True
        duration_ms = int((time.perf_counter() - t0) * 1000)
        _emit_tool_event(org, persona, row["name"], tool, duration_ms,
                         ok=True, size=len((content or "").encode()),
                         truncated=truncated)
        return {"ok": True, "content": content, "duration_ms": duration_ms}


def _emit_tool_event(org: str, persona: str, server: str, tool: str,
                     duration_ms: int, *, ok: bool, size: int,
                     truncated: bool = False) -> None:
    try:
        from pdlc_graph.llm_port import current_thread

        from ..clickstream.emitter import get_emitter

        thread = current_thread() or ""
        parts = thread.split(":")
        project = parts[1] if len(parts) > 1 else None
        get_emitter().emit(
            "tool.called",
            {"org_id": _uuid.UUID(org),
             "project_id": _uuid.UUID(project) if project else _uuid.UUID(int=0),
             "thread_id": thread or None, "actor": persona},
            {"agent_persona": persona, "server": server, "tool": tool,
             "duration_ms": duration_ms, "ok": ok, "bytes": size,
             "truncated": truncated},
            str(_uuid.uuid4()),
        )
    except Exception:  # audit must never break a tool call
        pass


def wire_mcp_backend(settings) -> bool:
    """Inject the MCP tool backend (flag-gated; registry data is inert without
    it). Returns True when wired."""
    if not getattr(settings, "wire_mcp", False):
        return False
    try:
        from pdlc_graph.tool_port import set_tool_backend

        from ..db.session import get_sync_engine

        set_tool_backend(MCPToolBackend(get_sync_engine(settings)))
        log.info("MCP tool backend wired (org tool servers active)")
        return True
    except Exception as exc:  # never block boot
        log.warning("MCP backend wiring failed (%s); agents stay toolless", exc)
        return False
