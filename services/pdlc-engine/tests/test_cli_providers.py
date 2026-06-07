"""Subscription-CLI providers (claude_code / codex / gemini_cli) — single-user
self-host only. The factory hard-guards them (opt-in flag + no auth), the builder
maps the tier to the CLI's --model, and the CLI model pipes the prompt on stdin.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest
from app.config import settings
from app.llm.factory import LLMProviderFactory, TenantCtx
from app.llm.providers.cli import CLIChatModel
from langchain_core.messages import HumanMessage, SystemMessage


def _get(persona="neo", tier="premium"):
    return LLMProviderFactory().get_model(persona=persona, tier=tier, tenant=TenantCtx("self-host"))


def test_cli_provider_refused_when_not_enabled(monkeypatch):
    monkeypatch.setattr(settings, "default_llm_provider", "claude_code")
    monkeypatch.setattr(settings, "enable_cli_providers", False)
    with pytest.raises(ValueError, match="PDLC_ENABLE_CLI_PROVIDERS"):
        _get()


def test_cli_provider_refused_in_multiuser(monkeypatch):
    monkeypatch.setattr(settings, "default_llm_provider", "codex")
    monkeypatch.setattr(settings, "enable_cli_providers", True)
    monkeypatch.setattr(settings, "auth_required", True)
    with pytest.raises(ValueError, match="multi-user / SaaS"):
        _get()


def test_cli_provider_builds_when_enabled_single_user(monkeypatch):
    monkeypatch.setattr(settings, "default_llm_provider", "claude_code")
    monkeypatch.setattr(settings, "enable_cli_providers", True)
    monkeypatch.setattr(settings, "auth_required", False)
    monkeypatch.setattr(settings, "claude_code_bin", "claude")
    model = _get(tier="premium")  # neo → premium → opus
    assert isinstance(model, CLIChatModel)
    assert model.command == ["claude", "-p", "--model", "opus"]


def test_codex_and_gemini_command_shapes(monkeypatch):
    monkeypatch.setattr(settings, "enable_cli_providers", True)
    monkeypatch.setattr(settings, "auth_required", False)
    monkeypatch.setattr(settings, "default_llm_provider", "codex")
    assert _get(tier="balanced").command == ["codex", "exec", "--model", "gpt-5.4"]
    monkeypatch.setattr(settings, "default_llm_provider", "gemini_cli")
    assert _get(tier="economy").command == ["gemini", "-m", "gemini-3.1-flash-lite"]


def test_cli_model_pipes_prompt_to_stdin(monkeypatch):
    captured = {}

    def fake_run(cmd, input=None, capture_output=None, text=None, timeout=None):
        captured["cmd"] = cmd
        captured["input"] = input
        return SimpleNamespace(returncode=0, stdout="agent reply\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    m = CLIChatModel(command=["claude", "-p", "--model", "opus"])
    out = m._call([SystemMessage(content="be terse"), HumanMessage(content="design the thing")])
    assert out == "agent reply"
    assert captured["cmd"] == ["claude", "-p", "--model", "opus"]
    assert "be terse" in captured["input"] and "design the thing" in captured["input"]


def test_cli_model_raises_on_nonzero_exit(monkeypatch):
    def fake_run(cmd, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="not logged in")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="not logged in"):
        CLIChatModel(command=["claude", "-p"])._call([HumanMessage(content="hi")])
