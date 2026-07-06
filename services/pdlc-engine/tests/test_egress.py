"""Egress network controls (PRD-08) — hermetic.

We assert CONFIGURATION, not connectivity: builders receive the right
http_client / client_kwargs / botocore Config for a given NetworkConfig, the
no_proxy exemptions match, header guardrails reject the credential channel,
and the boot report tells the truth. No network anywhere.
"""

from __future__ import annotations

import logging
import uuid
from typing import ClassVar

import pytest
from app.config import settings
from app.llm.factory import NetworkConfig, ProviderConfig, instance_network
from app.llm.providers import _net
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
ORG = str(uuid.uuid4())
TIERS = {"premium": "a", "balanced": "b", "economy": "c"}


@pytest.fixture(autouse=True)
def _clear_client_cache():
    _net._clients.cache_clear()
    yield
    _net._clients.cache_clear()


# ----- helpers ---------------------------------------------------------------


def test_no_proxy_suffix_matching():
    np = ("ollama.svc", ".internal", "localhost")
    assert _net.no_proxy_match("http://ollama.svc:11434", np)
    assert _net.no_proxy_match("http://gpu.internal:8000/v1", np)
    assert _net.no_proxy_match("http://localhost:11434", np)
    assert not _net.no_proxy_match("https://api.openai.com", np)
    assert not _net.no_proxy_match("https://api.openai.com", ())


def test_effective_proxy_and_clients():
    net = NetworkConfig(proxy_url="http://proxy.corp:3128", no_proxy=("localhost",))
    assert _net.effective_proxy(net, "https://api.anthropic.com") == "http://proxy.corp:3128"
    assert _net.effective_proxy(net, "http://localhost:8000") is None
    assert _net.httpx_clients(None) == (None, None)
    assert _net.httpx_clients(NetworkConfig()) == (None, None)  # nothing configured
    sync_c, async_c = _net.httpx_clients(net)
    assert sync_c is not None and async_c is not None
    # memoized per (proxy, ca) pair — no per-call client construction
    assert _net.httpx_clients(net)[0] is sync_c


def test_instance_network_from_settings(monkeypatch):
    assert instance_network() is None  # nothing configured → builders skip plumbing
    monkeypatch.setattr(settings, "egress_proxy_url", "http://proxy.corp:3128")
    monkeypatch.setattr(settings, "egress_no_proxy", "localhost, .svc")
    net = instance_network({"X-Gateway-Key": "route-a"})
    assert net.proxy_url == "http://proxy.corp:3128"
    assert net.no_proxy == ("localhost", ".svc")
    assert net.extra_headers == {"X-Gateway-Key": "route-a"}
    # headers alone also produce a config (gateway hints without a proxy)
    monkeypatch.setattr(settings, "egress_proxy_url", None)
    assert instance_network({"X-A": "1"}).extra_headers == {"X-A": "1"}
    assert instance_network() is None


# ----- builders receive the right kwargs --------------------------------------


class _FakeChat:
    last: ClassVar[dict] = {}

    def __init__(self, **kw):
        _FakeChat.last = kw


NET = NetworkConfig(proxy_url="http://proxy.corp:3128", ca_bundle=None,
                    extra_headers={"X-Gateway-Key": "route-a"})


def test_openai_family_builders_get_http_client_and_headers(monkeypatch):
    from app.llm.providers import anthropic as ap
    from app.llm.providers import openai as op
    from app.llm.providers import openai_compatible as oc

    monkeypatch.setattr("langchain_anthropic.ChatAnthropic", _FakeChat)
    ap.build(ProviderConfig(provider="anthropic", network=NET), "m")
    assert _FakeChat.last["http_client"] is not None
    assert _FakeChat.last["http_async_client"] is not None
    assert _FakeChat.last["default_headers"] == {"X-Gateway-Key": "route-a"}

    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChat)
    op.build(ProviderConfig(provider="openai", network=NET), "m")
    assert _FakeChat.last["http_client"] is not None

    oc.build(ProviderConfig(provider="openai_compatible",
                            endpoint="https://openrouter.ai/api/v1", network=NET), "m")
    assert _FakeChat.last["http_client"] is not None
    assert _FakeChat.last["default_headers"] == {"X-Gateway-Key": "route-a"}

    # no network config → no egress kwargs at all (byte-identical default path)
    op.build(ProviderConfig(provider="openai"), "m")
    assert "http_client" not in _FakeChat.last
    assert "default_headers" not in _FakeChat.last


def test_gateway_no_proxy_exemption(monkeypatch):
    from app.llm.providers import openai_compatible as oc

    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChat)
    net = NetworkConfig(proxy_url="http://proxy.corp:3128", no_proxy=("localhost",))
    oc.build(ProviderConfig(provider="openai_compatible",
                            endpoint="http://localhost:8000/v1", network=net), "m")
    assert "http_client" not in _FakeChat.last  # exempted → SDK default client


def test_ollama_builder_client_kwargs(monkeypatch):
    from app.llm.providers import ollama as olp

    monkeypatch.setattr("langchain_ollama.ChatOllama", _FakeChat)
    olp.build(ProviderConfig(provider="ollama", endpoint="http://gpu-box:11434",
                             network=NET), "llama3.3:70b")
    assert _FakeChat.last["client_kwargs"]["proxy"] == "http://proxy.corp:3128"
    assert _FakeChat.last["client_kwargs"]["headers"] == {"X-Gateway-Key": "route-a"}
    # in-cluster exemption
    net = NetworkConfig(proxy_url="http://proxy.corp:3128", no_proxy=("gpu-box",))
    olp.build(ProviderConfig(provider="ollama", endpoint="http://gpu-box:11434",
                             network=net), "llama3.3:70b")
    assert "proxy" not in _FakeChat.last.get("client_kwargs", {})


def test_bedrock_builder_botocore_proxies(monkeypatch):
    from app.llm.providers import bedrock as bp

    monkeypatch.setattr("langchain_aws.ChatBedrockConverse", _FakeChat)
    bp.build(ProviderConfig(provider="bedrock", region="us-east-1", network=NET), "m")
    cfg = _FakeChat.last["config"]
    assert cfg.proxies == {"http": "http://proxy.corp:3128",
                           "https": "http://proxy.corp:3128"}
    bp.build(ProviderConfig(provider="bedrock", region="us-east-1"), "m")
    assert "config" not in _FakeChat.last


def test_gemini_env_fallback_never_overwrites(monkeypatch):
    from app.llm.providers import gemini as gp

    monkeypatch.setattr("langchain_google_genai.ChatGoogleGenerativeAI", _FakeChat)
    monkeypatch.setenv("HTTPS_PROXY", "http://operator-set:8080")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    gp.build(ProviderConfig(provider="gemini",
                            network=NetworkConfig(proxy_url="http://proxy.corp:3128",
                                                  ca_bundle="/etc/ssl/corp.pem")), "m")
    import os
    assert os.environ["HTTPS_PROXY"] == "http://operator-set:8080"  # untouched
    assert os.environ["SSL_CERT_FILE"] == "/etc/ssl/corp.pem"       # filled (was unset)


# ----- header guardrails (DB-free route validation) -----------------------------


def test_extra_headers_guardrails():
    base = {"provider": "anthropic", "tier_map": TIERS}
    bad_sets = [
        {"Authorization": "Bearer sneak"},          # credential channel
        {"Host": "evil"},
        {"Cookie": "session=x"},
        {"Content-Type": "application/json"},
        {"Proxy-Authorization": "x"},
        {"X Bad Name": "v"},                        # name pattern
        {"X-Big": "v" * 513},                       # value size
        {f"X-{i}": "v" for i in range(9)},          # count
    ]
    for headers in bad_sets:
        r = client.put(f"/v1/admin/models/org-default?org_id={ORG}",
                       json={**base, "extra_headers": headers})
        assert r.status_code == 422, headers


# ----- boot report ---------------------------------------------------------------


def test_boot_egress_report(monkeypatch, caplog):
    from app.runtime.llm_backend import _log_egress_report

    _log_egress_report(settings)  # nothing configured → silent
    monkeypatch.setattr(settings, "egress_proxy_url", "http://proxy.corp:3128")
    monkeypatch.setattr(settings, "egress_ca_bundle", "/nonexistent/corp.pem")
    with caplog.at_level(logging.INFO, logger="pdlc.runtime.llm"):
        _log_egress_report(settings)
    text = caplog.text
    assert "unsupported: vertex" in text and "partial: bedrock" in text
    assert "does not exist" in text  # loud CA-path validation
