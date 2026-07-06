"""T3-5 per-org RPM quotas + T3-1 stdio MCP execution (hermetic half).

Quota: the limiter resolves a forced rpm without a DB lookup, caches per-org,
and the route validates. Stdio: call_tool dispatches to the stdio client for a
stdio-transport server (over an injected fake — no real subprocess) and remains
gated. DB-backed quota resolution is covered in the integration suite.
"""

from __future__ import annotations

import uuid

import pytest
from app.config import settings
from app.llm.rate_limit import RateLimit, invalidate_quota_cache
from app.main import app
from app.runtime import mcp_backend as MB
from app.runtime.mcp_backend import MCPToolBackend, reset_mcp_caches
from fastapi.testclient import TestClient
from pdlc_graph.ports import reset_current_org, set_current_org

client = TestClient(app)
ORG = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _clean():
    invalidate_quota_cache()
    reset_mcp_caches()
    MB.reset_call_client()
    MB.reset_stdio_client()
    yield
    invalidate_quota_cache()
    reset_mcp_caches()
    MB.reset_call_client()
    MB.reset_stdio_client()


# ----- T3-5 quotas -------------------------------------------------------------


def test_forced_rpm_skips_db_lookup():
    # An explicitly-passed rpm is a hard override (tests / forced config).
    rl = RateLimit(rpm=5)
    assert rl.effective_rpm(ORG) == 5
    assert rl.effective_rpm("any-other") == 5  # never per-org resolved


def test_effective_rpm_falls_back_to_global(monkeypatch):
    monkeypatch.setattr(settings, "llm_rpm_default", 42)
    monkeypatch.setattr(settings, "task_store", "memory")  # no DB → global default
    rl = RateLimit()  # unforced
    assert rl.effective_rpm(ORG) == 42


def test_quota_route_validation():
    # Pydantic validation (ge=0) happens before any DB access.
    r = client.put(f"/v1/admin/budget/quota?org_id={ORG}", json={"rpm_limit": -1})
    assert r.status_code == 422
    # (GET/PUT round-trip against real Postgres is in the integration suite.)


# ----- T3-1 stdio MCP execution ------------------------------------------------


STDIO_SERVER = {"id": "s1", "name": "fs", "transport": "stdio", "url": None,
                "command": "npx", "args": ["-y", "srv", "/data"],
                "auth_secret_ref": None, "allowed_tools": ["read_file"]}


def _backend(server, monkeypatch):
    monkeypatch.setattr(settings, "enable_stdio_mcp", True)
    monkeypatch.setattr(settings, "auth_required", False)
    b = MCPToolBackend(db=None)
    b._bound_servers = lambda org, persona, phase: [server]  # type: ignore[method-assign]
    return b


def test_stdio_tool_dispatches_to_stdio_client(monkeypatch):
    seen = {}

    def fake_stdio(command, args, tool, arguments, timeout_s):
        seen.update(command=command, args=args, tool=tool)
        return "file contents"

    MB.set_stdio_client(fake_stdio)
    b = _backend(STDIO_SERVER, monkeypatch)
    org = str(uuid.uuid4())
    tok = set_current_org(org)
    try:
        out = b.call_tool("bolt", "fs", "read_file", {"path": "x"})
    finally:
        reset_current_org(tok)
    assert out["ok"] is True and out["content"] == "file contents"
    assert seen == {"command": "npx", "args": ["-y", "srv", "/data"], "tool": "read_file"}


def test_stdio_refused_without_flag(monkeypatch):
    monkeypatch.setattr(settings, "enable_stdio_mcp", False)
    monkeypatch.setattr(settings, "auth_required", False)
    b = MCPToolBackend(db=None)
    b._bound_servers = lambda org, persona, phase: [STDIO_SERVER]  # type: ignore[method-assign]
    org = str(uuid.uuid4())
    tok = set_current_org(org)
    try:
        out = b.call_tool("bolt", "fs", "read_file", {"path": "x"})
    finally:
        reset_current_org(tok)
    assert out["ok"] is False and "PDLC_ENABLE_STDIO_MCP" in out["error"]
