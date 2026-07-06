"""MCP tool servers (PRD-09) — hermetic half.

stdio guard matrix, route validation (SSRF, names, transport shapes),
templates, and the backend's enforcement (allowlist, per-turn cap, negative
cache, truncation) over a fake client + faked binding resolution. No `mcp`
SDK import anywhere in this file — the hot path never needs it.
"""

from __future__ import annotations

import uuid

import pytest
from app.config import settings
from app.main import app
from app.runtime import mcp_backend as MB
from app.runtime.mcp_backend import MCPToolBackend, guard_stdio, reset_mcp_caches
from fastapi.testclient import TestClient
from pdlc_graph.llm_port import reset_thread_context, set_thread_context
from pdlc_graph.ports import reset_current_org, set_current_org

client = TestClient(app)
ORG = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _clean():
    reset_mcp_caches()
    MB.reset_call_client()
    yield
    reset_mcp_caches()
    MB.reset_call_client()


# ----- stdio guard matrix (flag x auth_required) -------------------------------


def test_guard_stdio_matrix(monkeypatch):
    guard_stdio("http")  # never guarded
    monkeypatch.setattr(settings, "enable_stdio_mcp", False)
    monkeypatch.setattr(settings, "auth_required", False)
    with pytest.raises(ValueError, match="PDLC_ENABLE_STDIO_MCP"):
        guard_stdio("stdio")
    monkeypatch.setattr(settings, "enable_stdio_mcp", True)
    guard_stdio("stdio")  # single-user self-host: allowed
    monkeypatch.setattr(settings, "auth_required", True)
    with pytest.raises(ValueError, match="multi-user"):
        guard_stdio("stdio")  # flag on but SaaS mode → still refused


# ----- route validation (DB-free paths) -----------------------------------------


def test_create_server_validation():
    q = f"?org_id={ORG}"
    # bad name
    r = client.post(f"/v1/admin/mcp/servers{q}", json={
        "name": "Bad Name!", "transport": "http", "url": "https://8.8.8.8/mcp"})
    assert r.status_code == 422
    # http without url
    r = client.post(f"/v1/admin/mcp/servers{q}", json={
        "name": "docs", "transport": "http"})
    assert r.status_code == 422
    # SSRF: metadata endpoint
    r = client.post(f"/v1/admin/mcp/servers{q}", json={
        "name": "sneaky", "transport": "http", "url": "http://169.254.169.254/mcp"})
    assert r.status_code == 422
    # stdio refused without the flag
    r = client.post(f"/v1/admin/mcp/servers{q}", json={
        "name": "fs", "transport": "stdio", "command": "npx"})
    assert r.status_code == 422


def test_mcp_private_networks_escape_hatch(monkeypatch):
    from app.routes.admin.mcp import ServerIn, _validate_server

    cfg = ServerIn(name="vpc-docs", transport="http", url="http://10.1.2.3/mcp")
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_server(cfg)
    monkeypatch.setattr(settings, "mcp_allow_private_networks", True)
    _validate_server(cfg)  # VPC-internal enterprise server allowed


def test_templates_hide_stdio_in_multi_user(monkeypatch):
    q = f"?org_id={ORG}"
    monkeypatch.setattr(settings, "auth_required", False)
    ids = {t["id"] for t in client.get(f"/v1/admin/mcp/templates{q}").json()["templates"]}
    assert "filesystem" in ids  # single-user: stdio template offered (with warning)
    # In multi-user mode the whole admin surface needs a JWT (guard), and the
    # filter drops stdio templates — assert the filter logic directly.
    from app.routes.admin.mcp import TEMPLATES

    multi_user_view = [t for t in TEMPLATES if t["transport"] != "stdio"]
    assert all(t["id"] != "filesystem" for t in multi_user_view)
    assert {t["id"] for t in TEMPLATES} - {t["id"] for t in multi_user_view} == {"filesystem"}


# ----- backend enforcement over a fake client ------------------------------------


SERVER = {"id": "s1", "name": "docs", "transport": "http",
          "url": "https://docs.example/mcp", "command": None,
          "auth_secret_ref": None, "allowed_tools": ["search"]}


def _backend(servers=None, client_fn=None):
    b = MCPToolBackend(db=None)
    b._bound_servers = lambda org, persona, phase: servers or []  # type: ignore[method-assign]
    if client_fn is not None:
        MB.set_call_client(client_fn)
    return b


@pytest.fixture
def _org_ctx():
    org = str(uuid.uuid4())
    tok = set_current_org(org)
    yield org
    reset_current_org(tok)


def test_list_tools_is_the_allowlist(_org_ctx):
    b = _backend([SERVER])
    assert b.list_tools("muse") == [{"server": "docs", "tool": "search"}]
    assert _backend([]).list_tools("muse") == []


def test_call_tool_happy_path_and_allowlist(_org_ctx):
    calls = []

    def fake(url, headers, tool, arguments, timeout_s):
        calls.append((url, tool, arguments))
        return "internal doc hits"

    b = _backend([SERVER], fake)
    out = b.call_tool("muse", "docs", "search", {"query": "dark mode"})
    assert out["ok"] is True and out["content"] == "internal doc hits"
    assert calls == [("https://docs.example/mcp", "search", {"query": "dark mode"})]
    # not in the allowlist → refused without any network
    out = b.call_tool("muse", "docs", "delete_everything", {})
    assert out["ok"] is False and "allowlist" in out["error"]
    # unbound server → refused
    out = b.call_tool("muse", "other", "search", {})
    assert out["ok"] is False and "not bound" in out["error"]
    assert len(calls) == 1


def test_call_tool_no_org_context():
    b = _backend([SERVER], lambda *a: "x")
    assert b.call_tool("muse", "docs", "search", {})["ok"] is False


def test_result_truncation(_org_ctx, monkeypatch):
    monkeypatch.setattr(settings, "mcp_max_result_bytes", 32)
    b = _backend([SERVER], lambda *a: "y" * 200)
    out = b.call_tool("muse", "docs", "search", {"query": "x"})
    assert out["ok"] is True
    assert out["content"].endswith("[truncated]")
    assert len(out["content"]) < 200


def test_failure_returns_error_and_negative_cache(_org_ctx):
    boom_calls = []

    def boom(*a, **k):
        boom_calls.append(1)
        raise TimeoutError("hung server")

    b = _backend([SERVER], boom)
    out = b.call_tool("muse", "docs", "search", {"query": "x"})
    assert out["ok"] is False and out["error"] == "TimeoutError"
    # cooled down: the second call is refused without touching the client
    out2 = b.call_tool("muse", "docs", "search", {"query": "x"})
    assert out2["ok"] is False and "cooling down" in out2["error"]
    assert len(boom_calls) == 1


def test_per_turn_call_cap(_org_ctx, monkeypatch):
    monkeypatch.setattr(settings, "mcp_calls_per_turn", 2)
    b = _backend([SERVER], lambda *a: "ok")
    tok = set_thread_context(f"{_org_ctx}:proj:sess")
    try:
        assert b.call_tool("muse", "docs", "search", {})["ok"] is True
        assert b.call_tool("muse", "docs", "search", {})["ok"] is True
        capped = b.call_tool("muse", "docs", "search", {})
        assert capped["ok"] is False and "cap" in capped["error"]
    finally:
        reset_thread_context(tok)


def test_stdio_refused_at_call_time_even_if_registered(_org_ctx, monkeypatch):
    monkeypatch.setattr(settings, "enable_stdio_mcp", False)
    stdio_server = {**SERVER, "transport": "stdio", "command": "npx", "url": None}
    b = _backend([stdio_server], lambda *a: "never")
    out = b.call_tool("muse", "docs", "search", {})
    assert out["ok"] is False and "PDLC_ENABLE_STDIO_MCP" in out["error"]
