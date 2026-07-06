"""Resilient LLM routing (PRD-05) — hermetic half.

Error classification, circuit-breaker semantics over a fake Redis with a
controllable clock, the real fixed-window rate limiter, the backend's
candidate loop (failover / no-failover / breaker gating / serving labels),
first-token streaming failover, and the chain API's DB-free validation.
"""

from __future__ import annotations

import uuid

import pytest
from app.config import settings
from app.llm.breaker import CircuitBreaker, breaker_key, set_breaker
from app.llm.errors import classify
from app.llm.rate_limit import RateLimit, RateLimited, set_rate_limit
from app.runtime.llm_backend import FactoryCompletionBackend

ORG = str(uuid.uuid4())


# ----- fake redis with a controllable clock -----------------------------------


class FakeRedis:
    def __init__(self):
        self.now = 1000.0
        self._data: dict[str, str] = {}
        self._exp: dict[str, float] = {}

    def tick(self, seconds: float) -> None:
        self.now += seconds

    def _alive(self, key: str) -> bool:
        exp = self._exp.get(key)
        if exp is not None and exp <= self.now:
            self._data.pop(key, None)
            self._exp.pop(key, None)
            return False
        return key in self._data

    def get(self, key):
        return self._data.get(key) if self._alive(key) else None

    def set(self, key, value, nx=False, ex=None):
        if nx and self._alive(key):
            return None
        self._data[key] = str(value)
        if ex is not None:
            self._exp[key] = self.now + ex
        else:
            self._exp.pop(key, None)
        return True

    def incr(self, key):
        cur = int(self._data[key]) if self._alive(key) else 0
        self._data[key] = str(cur + 1)
        return cur + 1

    def expire(self, key, seconds):
        if self._alive(key):
            self._exp[key] = self.now + seconds
        return True

    def delete(self, *keys):
        for k in keys:
            self._data.pop(k, None)
            self._exp.pop(k, None)


class ExplodingRedis:
    def __getattr__(self, name):
        def _boom(*a, **k):
            raise ConnectionError("redis down")
        return _boom


@pytest.fixture(autouse=True)
def _clean_singletons():
    set_breaker(None)
    set_rate_limit(None)
    yield
    set_breaker(None)
    set_rate_limit(None)


# ----- error classification ----------------------------------------------------


class _S(Exception):
    def __init__(self, status):
        self.status_code = status


def _named(name):
    return type(name, (Exception,), {})()


def test_classify_taxonomy():
    assert classify(_S(429)) == "retriable"
    assert classify(_S(500)) == "retriable"
    assert classify(_S(503)) == "retriable"
    assert classify(TimeoutError()) == "retriable"
    assert classify(ConnectionError()) == "retriable"
    assert classify(_named("APIConnectionError")) == "retriable"
    assert classify(_named("RateLimitError")) == "retriable"
    assert classify(_named("ThrottlingException")) == "retriable"
    assert classify(_S(401)) == "auth"
    assert classify(_S(403)) == "auth"
    assert classify(_named("AuthenticationError")) == "auth"
    assert classify(_named("AccessDeniedException")) == "auth"
    assert classify(_S(400)) == "fatal"
    assert classify(_S(404)) == "fatal"
    assert classify(_S(422)) == "fatal"
    assert classify(_named("SomeRandomError")) == "fatal"  # default: fail closed


def test_breaker_key_distinguishes_gateways():
    assert breaker_key("anthropic", None) == "anthropic"
    assert breaker_key("openai_compatible", "https://openrouter.ai/api/v1") == \
        "openai_compatible:openrouter.ai"
    assert breaker_key("openai_compatible", "http://localhost:8000/v1") == \
        "openai_compatible:localhost"


# ----- circuit breaker ----------------------------------------------------------


def _breaker(r, **kw):
    return CircuitBreaker(r, threshold=3, window_s=60, cooldown_s=30, **kw)


def test_breaker_trips_after_threshold_and_recovers():
    r = FakeRedis()
    transitions: list = []
    b = _breaker(r, on_transition=lambda k, t: transitions.append(t))
    assert b.allow(ORG, "anthropic")
    for _ in range(3):
        b.record_failure(ORG, "anthropic")
    assert transitions == ["open"]
    assert not b.allow(ORG, "anthropic")  # open → skipped

    r.tick(31)  # cooldown lapses → half-open
    assert b.allow(ORG, "anthropic") is True   # the single probe
    assert b.allow(ORG, "anthropic") is False  # second caller blocked
    b.record_success(ORG, "anthropic")         # probe succeeded → closed
    assert transitions == ["open", "close"]
    assert b.allow(ORG, "anthropic")


def test_breaker_reopens_on_failed_probe():
    r = FakeRedis()
    transitions: list = []
    b = _breaker(r, on_transition=lambda k, t: transitions.append(t))
    for _ in range(3):
        b.record_failure(ORG, "openai")
    r.tick(31)
    assert b.allow(ORG, "openai")       # half-open probe admitted
    b.record_failure(ORG, "openai")     # probe failed
    assert transitions == ["open", "reopen"]
    assert not b.allow(ORG, "openai")   # open again


def test_breaker_failure_window_expires():
    r = FakeRedis()
    b = _breaker(r)
    b.record_failure(ORG, "gemini")
    b.record_failure(ORG, "gemini")
    r.tick(61)  # window lapses — old failures forgotten
    b.record_failure(ORG, "gemini")
    assert b.allow(ORG, "gemini")  # 1 < threshold → still closed


def test_breaker_fails_open_without_redis():
    b = CircuitBreaker(ExplodingRedis())
    assert b.allow(ORG, "anthropic") is True
    b.record_failure(ORG, "anthropic")  # no raise
    b.record_success(ORG, "anthropic")  # no raise


def test_breaker_is_org_scoped():
    r = FakeRedis()
    b = _breaker(r)
    for _ in range(3):
        b.record_failure("org-a", "anthropic")
    assert not b.allow("org-a", "anthropic")
    assert b.allow("org-b", "anthropic")


# ----- rate limiter --------------------------------------------------------------


def test_rate_limit_fixed_window(monkeypatch):
    r = FakeRedis()
    rl = RateLimit(r, rpm=3)
    monkeypatch.setattr("time.time", lambda: 60_000.0)
    assert all(rl.acquire(ORG, "openai", "premium") for _ in range(3))
    assert rl.acquire(ORG, "openai", "premium") is False       # 4th in the minute
    assert rl.acquire(ORG, "openai", "economy") is True        # separate bucket
    monkeypatch.setattr("time.time", lambda: 60_060.0)         # next minute
    assert rl.acquire(ORG, "openai", "premium") is True


def test_rate_limit_fails_open():
    assert RateLimit(ExplodingRedis(), rpm=1).acquire(ORG, "openai", "premium")


# ----- backend candidate loop -----------------------------------------------------


class _Result:
    def __init__(self, content):
        self.content = content
        self.usage_metadata = {"input_tokens": 10, "output_tokens": 5}


class _Model:
    """Scripted model: raises `exc` if set, else returns/streams content."""

    def __init__(self, content="ok", exc=None, chunks=None):
        self._content, self._exc, self._chunks = content, exc, chunks

    def invoke(self, _messages):
        if self._exc is not None:
            raise self._exc
        return _Result(self._content)

    def stream(self, _messages):
        if self._exc is not None:
            raise self._exc
        for c in self._chunks or [self._content]:
            if isinstance(c, Exception):
                raise c
            yield _Result(c)


class _ChainFactory:
    """resolve() serves the primary; failover_candidates serves the chain."""

    def __init__(self, primary: _Model, chain: list[tuple[_Model, str, str, str | None]]):
        self._primary = primary
        self._chain = chain
        self.chain_queried = 0

    def resolve(self, persona, tier, tenant):
        return self._primary, "anthropic", "claude-opus-4-8"

    def failover_candidates(self, tier, tenant):
        self.chain_queried += 1
        return [lambda c=c: c for c in self._chain]


def _backend(primary, chain=(), redis=None):
    set_breaker(CircuitBreaker(redis or FakeRedis(), threshold=3, window_s=60, cooldown_s=30))
    return FactoryCompletionBackend(_ChainFactory(primary, list(chain)), org_id=ORG)


def test_happy_path_never_queries_the_chain():
    f = _ChainFactory(_Model("hello"), [])
    b = FactoryCompletionBackend(f, org_id=ORG)
    assert b.complete("neo", "hi") == "hello"
    assert f.chain_queried == 0  # zero extra work on the hot path


def test_retriable_failure_fails_over_to_next_candidate():
    fb = (_Model("served-by-bedrock"), "bedrock", "anthropic.claude-sonnet-4-6", None)
    b = _backend(_Model(exc=_S(503)), [fb])
    assert b.complete("neo", "hi") == "served-by-bedrock"


def test_auth_failure_never_fails_over():
    fb = (_Model("nope"), "bedrock", "m", None)
    b = _backend(_Model(exc=_S(401)), [fb])
    with pytest.raises(_S):
        b.complete("neo", "hi")


def test_fatal_failure_never_fails_over():
    fb = (_Model("nope"), "bedrock", "m", None)
    b = _backend(_Model(exc=_S(400)), [fb])
    with pytest.raises(_S):
        b.complete("neo", "hi")


def test_exhausted_chain_raises_last_error():
    last = _S(502)
    b = _backend(_Model(exc=_S(503)), [
        (_Model(exc=_S(500)), "bedrock", "m1", None),
        (_Model(exc=last), "openai", "m2", None),
    ])
    with pytest.raises(_S) as ei:
        b.complete("neo", "hi")
    assert ei.value is last


def test_fatal_error_mid_chain_stops_the_chain():
    b = _backend(_Model(exc=_S(503)), [
        (_Model(exc=_S(404)), "bedrock", "m1", None),   # fatal — stop here
        (_Model("never"), "openai", "m2", None),
    ])
    with pytest.raises(_S) as ei:
        b.complete("neo", "hi")
    assert ei.value.status_code == 404


def test_open_breaker_skips_fallback_candidate():
    r = FakeRedis()
    b = _backend(_Model(exc=_S(503)), [
        (_Model("skipped"), "bedrock", "m1", None),
        (_Model("served"), "openai", "m2", None),
    ], redis=r)
    from app.llm.breaker import get_breaker
    for _ in range(3):
        get_breaker().record_failure(ORG, "bedrock")  # trip bedrock's breaker
    assert b.complete("neo", "hi") == "served"


def test_broken_fallback_entry_is_skipped():
    def boom():
        raise RuntimeError("dangling secret_ref")
    fb_ok = (_Model("served"), "openai", "m2", None)
    set_breaker(CircuitBreaker(FakeRedis(), threshold=3))
    f = _ChainFactory(_Model(exc=_S(503)), [fb_ok])
    f.failover_candidates = lambda tier, tenant: [boom, lambda: fb_ok]  # type: ignore[assignment]
    b = FactoryCompletionBackend(f, org_id=ORG)
    assert b.complete("neo", "hi") == "served"


def test_rate_limited_raises_and_never_fails_over(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    set_rate_limit(RateLimit(FakeRedis(), rpm=0))  # everything rejected
    fb = (_Model("nope"), "bedrock", "m", None)
    b = _backend(_Model("primary"), [fb])
    with pytest.raises(RateLimited):
        b.complete("neo", "hi")


def test_failover_kill_switch(monkeypatch):
    monkeypatch.setattr(settings, "llm_failover_enabled", False)
    fb = (_Model("nope"), "bedrock", "m", None)
    b = _backend(_Model(exc=_S(503)), [fb])
    with pytest.raises(_S):
        b.complete("neo", "hi")


# ----- streaming -----------------------------------------------------------------


def test_stream_fails_over_before_first_token():
    fb = (_Model(chunks=["a", "b"]), "bedrock", "m", None)
    b = _backend(_Model(exc=_S(503)), [fb])
    assert list(b.stream("neo", "hi")) == ["a", "b"]


def test_stream_never_fails_over_after_first_token():
    err = _S(503)
    fb = (_Model("nope"), "bedrock", "m", None)
    b = _backend(_Model(chunks=["first", err]), [fb])
    out = []
    with pytest.raises(_S):
        for t in b.stream("neo", "hi"):
            out.append(t)
    assert out == ["first"]  # partial output surfaced, then the error — no splicing


# ----- chain API validation (DB-free paths) ----------------------------------------


def test_chain_api_validation():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    org = str(uuid.uuid4())
    tiers = {"premium": "a", "balanced": "b", "economy": "c"}
    base = {"provider": "anthropic", "tier_map": tiers}

    # openai_compatible chain entry without tier_map → 422 before any DB access
    r = client.put(f"/v1/admin/models/org-default?org_id={org}", json={
        **base, "failover_chain": [
            {"provider": "openai_compatible", "endpoint": "https://8.8.8.8/v1"}]})
    assert r.status_code == 422
    # private endpoint in a chain entry → SSRF rejection
    r = client.put(f"/v1/admin/models/org-default?org_id={org}", json={
        **base, "failover_chain": [
            {"provider": "openai_compatible", "endpoint": "http://10.0.0.1/v1",
             "tier_map": tiers}]})
    assert r.status_code == 422
    # more than 3 entries → schema rejection
    r = client.put(f"/v1/admin/models/org-default?org_id={org}", json={
        **base, "failover_chain": [{"provider": "bedrock"}] * 4})
    assert r.status_code == 422
