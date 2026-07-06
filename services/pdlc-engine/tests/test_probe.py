"""Provider health & connectivity testing (hermetic half).

Error taxonomy, SSRF guard, the injectable prober port, the candidate-test
route (no DB touched on that path), rate limiting, and /health/ready's llm
field. Saved-scope probes + health-table persistence live in the integration
suite (they need Postgres).
"""

from __future__ import annotations

import uuid

import pytest
from app.config import settings
from app.llm import probe
from app.llm.probe import (
    EndpointNotAllowed,
    ProbeResult,
    classify_error,
    validate_endpoint,
)
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
ORG = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _fresh_probe_state():
    probe.reset_prober()
    probe.reset_probe_limiter()
    probe.reset_instance_status()
    yield
    probe.reset_prober()
    probe.reset_probe_limiter()
    probe.reset_instance_status()


# ----- error taxonomy --------------------------------------------------------


class _Exc(Exception):
    def __init__(self, msg="", status_code=None):
        super().__init__(msg)
        if status_code is not None:
            self.status_code = status_code


def _named(name: str, msg: str = "", **attrs):
    exc_type = type(name, (Exception,), {})
    exc = exc_type(msg)
    for k, v in attrs.items():
        setattr(exc, k, v)
    return exc


def test_classify_error_taxonomy():
    assert classify_error(TimeoutError()) == "timeout"
    assert classify_error(_named("ReadTimeout")) == "timeout"
    assert classify_error(ConnectionError()) == "endpoint_unreachable"
    assert classify_error(_named("APIConnectionError")) == "endpoint_unreachable"
    assert classify_error(_named("AuthenticationError")) == "auth_error"
    assert classify_error(_Exc(status_code=401)) == "auth_error"
    assert classify_error(_named("UnrecognizedClientException")) == "auth_error"
    assert classify_error(_named("AccessDeniedException")) == "access_denied"
    assert classify_error(_Exc(status_code=403)) == "access_denied"
    assert classify_error(_named("NotFoundError")) == "model_not_found"
    assert classify_error(_Exc(status_code=404)) == "model_not_found"
    assert classify_error(_named("RateLimitError")) == "rate_limited"
    assert classify_error(_Exc(status_code=429)) == "rate_limited"
    assert classify_error(_named("ThrottlingException")) == "rate_limited"
    # Bedrock reports a bad modelId as ValidationException.
    assert classify_error(_named("ValidationException",
                                 "The provided model identifier is invalid")) == "model_not_found"
    assert classify_error(_named("ValidationException", "bad temperature")) == "bad_request"
    assert classify_error(_Exc(status_code=400)) == "bad_request"
    assert classify_error(_named("SomethingWeird")) == "unknown"


def test_every_error_class_has_a_sanitized_message():
    for cls in probe.ERROR_CLASSES:
        assert probe.MESSAGES[cls]


# ----- SSRF guard -------------------------------------------------------------


def test_ssrf_guard_blocks_private_space():
    for bad in (
        "http://127.0.0.1:11434",          # loopback
        "http://10.0.0.5/v1",              # RFC-1918
        "http://192.168.1.10:8080",        # RFC-1918
        "http://169.254.169.254/latest",   # cloud metadata (link-local)
        "ftp://api.example.com",           # scheme
    ):
        with pytest.raises(EndpointNotAllowed):
            validate_endpoint(bad)


def test_ssrf_guard_allows_public_and_none():
    validate_endpoint(None)                    # no endpoint at all
    validate_endpoint("https://8.8.8.8/v1")    # public IP literal — no DNS needed


def test_ssrf_guard_escape_hatch(monkeypatch):
    monkeypatch.setattr(settings, "allow_private_llm_endpoints", True)
    validate_endpoint("http://127.0.0.1:11434")  # self-host Ollama


def test_ssrf_guard_blocks_dns_to_private(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("10.9.8.7", 0))],
    )
    with pytest.raises(EndpointNotAllowed):
        validate_endpoint("https://innocent-looking.example.com")


# ----- injectable prober + route ---------------------------------------------


def test_candidate_probe_route_uses_injected_prober():
    seen: dict = {}

    def fake(cfg, model_id, timeout_s):
        seen.update(provider=cfg.provider, key=cfg.secret_value,
                    model=model_id, timeout=timeout_s)
        return ProbeResult(ok=True, latency_ms=42, tested_model=model_id)

    probe.set_prober(fake)
    r = client.post(f"/v1/admin/models/test?org_id={ORG}", json={
        "provider": "anthropic", "model_id": "claude-sonnet-4-6",
        "api_key": "sk-probe-once"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["latency_ms"] == 42
    assert body["tested_model"] == "claude-sonnet-4-6"
    assert seen == {"provider": "anthropic", "key": "sk-probe-once",
                    "model": "claude-sonnet-4-6", "timeout": settings.llm_probe_timeout_s}
    assert "sk-probe-once" not in r.text  # inline key used once, never echoed


def test_candidate_probe_defaults_model_from_tier():
    probe.set_prober(lambda cfg, m, t: ProbeResult(ok=True, tested_model=m))
    r = client.post(f"/v1/admin/models/test?org_id={ORG}",
                    json={"provider": "openai", "tier": "economy"})
    assert r.json()["tested_model"] == "gpt-5.4-mini"


def test_candidate_probe_requires_provider():
    r = client.post(f"/v1/admin/models/test?org_id={ORG}", json={})
    assert r.status_code == 422


def test_forbidden_endpoint_short_circuits_probe():
    calls = []
    probe.set_prober(lambda *a: calls.append(a) or ProbeResult(ok=True))
    r = client.post(f"/v1/admin/models/test?org_id={ORG}", json={
        "provider": "ollama", "model_id": "llama3",
        "endpoint": "http://169.254.169.254/v1"})
    assert r.status_code == 200
    assert r.json()["error_class"] == "endpoint_forbidden"
    assert calls == []  # never probed


def test_probe_rate_limit_per_org():
    probe.set_prober(lambda cfg, m, t: ProbeResult(ok=True, tested_model=m))
    org = str(uuid.uuid4())
    for _ in range(probe.PROBE_LIMIT_PER_MIN):
        assert client.post(f"/v1/admin/models/test?org_id={org}",
                           json={"provider": "openai"}).status_code == 200
    assert client.post(f"/v1/admin/models/test?org_id={org}",
                       json={"provider": "openai"}).status_code == 429
    # A different org is unaffected (per-org window).
    assert client.post(f"/v1/admin/models/test?org_id={uuid.uuid4()}",
                       json={"provider": "openai"}).status_code == 200


def test_real_prober_timeout_budget():
    import time as _t

    def slow_builder(cfg, model_id):
        class _M:
            def bind(self, **kw):
                return self

            def invoke(self, _msg):
                _t.sleep(5)

        return _M()

    from app.llm import factory as F
    original = F._BUILDERS["openai"]
    F._BUILDERS["openai"] = slow_builder
    try:
        from app.llm.factory import ProviderConfig
        r = probe._real_probe(ProviderConfig(provider="openai"), "m", timeout_s=0.2)
    finally:
        F._BUILDERS["openai"] = original
    assert r.ok is False and r.error_class == "timeout"


# ----- /health/ready ----------------------------------------------------------


def test_health_ready_llm_status():
    assert client.get("/health/ready").json()["checks"]["llm"] == "unprobed"
    probe.record_instance_probe(ProbeResult(ok=True, latency_ms=100))
    assert client.get("/health/ready").json()["checks"]["llm"] == "ok"
    probe.record_instance_probe(probe.failure("auth_error"))
    assert client.get("/health/ready").json()["checks"]["llm"] == "degraded"


# ----- GET /admin/models/defaults (console prefill data) ----------------------


def test_model_defaults_endpoint():
    r = client.get(f"/v1/admin/models/defaults?org_id={ORG}")
    assert r.status_code == 200
    body = r.json()
    assert body["providers"] == [
        "bedrock", "anthropic", "vertex", "azure", "openai", "gemini", "ollama"]
    assert not {"claude_code", "codex", "gemini_cli"} & set(body["providers"])
    assert len(body["personas"]) == 10 and "sentinel" in body["personas"]
    assert set(body["tier_maps"]) == set(body["providers"])
    for m in body["tier_maps"].values():
        assert set(m) == {"premium", "balanced", "economy"}
    assert body["instance_default"]["provider"] == settings.default_llm_provider
