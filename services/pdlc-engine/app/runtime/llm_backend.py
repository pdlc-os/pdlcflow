"""LLM backend adapter — bridges the engine's provider factory into the graph.

pdlc-graph nodes call `llm_port.complete(persona, prompt)` and never import the
engine. At boot the engine installs a factory-backed implementation so personas
resolve through `LLMProviderFactory` (two-level org/agent config → provider →
model). It is wired ONLY when explicitly enabled, so dev/test keep the
deterministic offline stub (no creds, no network, no model drift).

Resilient routing (PRD-05) lives HERE, not in the factory: the factory stays a
pure config→model resolver; this backend owns the retry loop because it
already owns spans, timing, usage extraction, and error handling.

  - Candidate 0 is exactly the pre-failover resolution (agent override → org
    default → instance default → fallback). Candidates 1..n come from the
    org's `failover_chain`, queried ONLY after a retriable primary failure —
    orgs without a chain pay zero extra work and behave byte-identically.
  - Error taxonomy (app/llm/errors.classify): 429/5xx/timeouts/connection →
    try next candidate; auth/validation → surface immediately (config bug,
    not incident — a doomed request must not burn the chain).
  - Circuit breaker gates FALLBACK candidates only (the primary is always
    attempted — a breaker that locks out a chainless org's only provider
    would be worse than the outage it guards against).
  - Rate limiting (off by default) charges one token per ATTEMPT — each
    attempt is a real upstream call. Rejection raises RateLimited: our own
    quota is not a provider incident, so it never triggers failover.
  - Streaming: failover applies only until the first content token has been
    yielded. After that, an error propagates — splicing two models' prose
    into one artifact is worse than a visible failure.
"""

from __future__ import annotations

import contextlib
import logging
import time

from .. import observability
from ..config import settings
from ..llm.breaker import breaker_key, get_breaker
from ..llm.errors import classify
from ..llm.factory import LLMProviderFactory, TenantCtx
from ..llm.rate_limit import RateLimited, get_rate_limit

log = logging.getLogger("pdlc.runtime.llm")

# The tier is resolved upstream in llm_port.complete() from each persona's
# soul-spec frontmatter, so a real tier always arrives here; this is just the
# safety net if a caller passes tier=None explicitly. The factory's tier_map
# turns the tier into a concrete per-provider model.
_DEFAULT_TIER = "premium"


class FactoryCompletionBackend:
    def __init__(self, factory: LLMProviderFactory, org_id: str | None = None) -> None:
        self._factory = factory
        self._org_id = org_id

    def _tenant(self) -> TenantCtx:
        # The authoritative tenant for this turn (the runner binds it from the
        # thread id). Per-tenant/per-agent LLM config in the DB keys off this, so
        # each org's overrides apply. Falls back to the bound org for non-turn calls.
        from pdlc_graph.ports import current_org

        org = current_org()
        if org in ("default", "self-host") and self._org_id:
            org = self._org_id
        return TenantCtx(org_id=org)

    def _resolve(self, persona: str, tier: str | None):
        """Return (model, provider, model_id) for this persona/tier/tenant.

        Prefers the factory's `resolve()` (which also yields provider + model_id
        for span/cost labelling); falls back to `get_model()` for any injected
        factory that predates it, labelling the call as unknown."""
        eff_tier = tier or _DEFAULT_TIER
        if hasattr(self._factory, "resolve"):
            return self._factory.resolve(persona=persona, tier=eff_tier, tenant=self._tenant())  # type: ignore[arg-type]
        model = self._factory.get_model(persona=persona, tier=eff_tier, tenant=self._tenant())  # type: ignore[arg-type]
        return model, "unknown", "unknown"

    def _model(self, persona: str, tier: str | None):
        return self._resolve(persona, tier)[0]

    def _fallbacks(self, eff_tier: str) -> list:
        """Chain builders for the tenant (empty when disabled/unsupported)."""
        if not getattr(settings, "llm_failover_enabled", True):
            return []
        if not hasattr(self._factory, "failover_candidates"):
            return []
        try:
            return self._factory.failover_candidates(eff_tier, self._tenant())  # type: ignore[arg-type]
        except Exception as exc:  # a broken chain must not break the turn
            log.warning("failover chain unavailable: %s", type(exc).__name__)
            return []

    def _pricing_overrides(self, org: str) -> dict | None:
        """Org price-sheet overrides for cost labelling (PRD-07); cached in the
        factory with a short TTL. Never breaks a completion."""
        if not hasattr(self._factory, "pricing_overrides"):
            return None
        try:
            return self._factory.pricing_overrides(org)  # type: ignore[union-attr]
        except Exception:
            return None

    def _check_rate_limit(self, org: str, provider: str, eff_tier: str) -> None:
        if not getattr(settings, "rate_limit_enabled", False):
            return
        rl = get_rate_limit()
        if not rl.acquire(org, provider, eff_tier):
            observability.record_rate_limited(provider, eff_tier)
            _emit_resilience("llm.rate_limited", org,
                             {"provider": provider, "tier": eff_tier, "rpm": rl.rpm})
            raise RateLimited(org, provider, eff_tier, rl.rpm)

    @staticmethod
    def _messages(system: str | None, prompt: str) -> list:
        messages: list = []
        if system:
            messages.append(("system", system))
        messages.append(("human", prompt))
        return messages

    def complete(
        self, persona: str, prompt: str, *, tier: str | None = None, system: str | None = None
    ) -> str:
        eff_tier = tier or _DEFAULT_TIER
        org = self._tenant().org_id
        messages = self._messages(system, prompt)
        overrides = self._pricing_overrides(org)

        # ----- primary attempt (the pre-failover hot path) -----
        model, provider, model_id = self._resolve(persona, tier)
        self._check_rate_limit(org, provider, eff_tier)
        t0 = time.perf_counter()
        with observability.llm_span(persona, eff_tier) as span:
            try:
                result = model.invoke(messages)
            except Exception as exc:
                self._record(span, persona, provider, model_id, eff_tier,
                             {"input": 0, "output": 0}, t0, ok=False, overrides=overrides)
                if span is not None:
                    with contextlib.suppress(Exception):
                        span.record_exception(exc)
                primary_exc: Exception = exc
            else:
                usage = _usage_from_message(result)
                self._record(span, persona, provider, model_id, eff_tier, usage, t0, ok=True, overrides=overrides)
                return getattr(result, "content", str(result))

        if classify(primary_exc) != "retriable":
            raise primary_exc
        fallbacks = self._fallbacks(eff_tier)
        if not fallbacks:
            raise primary_exc

        # ----- failover loop -----
        last_exc: Exception = primary_exc
        failed_provider = provider
        for rank, build in enumerate(fallbacks, start=1):
            observability.record_fallback(failed_provider, type(last_exc).__name__)
            _emit_resilience("llm.failover", org,
                             {"from_provider": failed_provider,
                              "reason": type(last_exc).__name__, "attempt": rank})
            try:
                model, provider, model_id, endpoint = build()
            except Exception as exc:
                log.warning("skipping broken fallback #%d: %s", rank, type(exc).__name__)
                continue
            bkey = breaker_key(provider, endpoint)
            breaker = get_breaker()
            if not breaker.allow(org, bkey):
                log.info("breaker open for %s — skipping fallback #%d", bkey, rank)
                continue
            self._check_rate_limit(org, provider, eff_tier)
            t0 = time.perf_counter()
            with observability.llm_span(persona, eff_tier) as span:
                if span is not None:
                    with contextlib.suppress(Exception):
                        span.set_attribute("pdlc.llm.fallback_rank", rank)
                try:
                    result = model.invoke(messages)
                except Exception as exc:
                    self._record(span, persona, provider, model_id, eff_tier,
                                 {"input": 0, "output": 0}, t0, ok=False, overrides=overrides)
                    if span is not None:
                        with contextlib.suppress(Exception):
                            span.record_exception(exc)
                    breaker.record_failure(org, bkey)
                    if classify(exc) != "retriable":
                        raise
                    last_exc, failed_provider = exc, provider
                    continue
                usage = _usage_from_message(result)
                breaker.record_success(org, bkey)
                # Serving labels are the FALLBACK's provider/model (FR-8).
                self._record(span, persona, provider, model_id, eff_tier, usage, t0, ok=True, overrides=overrides)
                return getattr(result, "content", str(result))
        raise last_exc

    def stream(
        self, persona: str, prompt: str, *, tier: str | None = None, system: str | None = None
    ):
        """Yield text chunks as the model streams (powers live token streaming).

        Failover window = until the first content token is yielded; after that
        an error propagates as it does today (no mid-stream model splicing)."""
        eff_tier = tier or _DEFAULT_TIER
        org = self._tenant().org_id
        messages = self._messages(system, prompt)
        overrides = self._pricing_overrides(org)

        def _primary():
            m, p, mid = self._resolve(persona, tier)
            return m, p, mid, None

        queue: list[tuple[int, object]] = [(0, _primary)]
        fallbacks_loaded = False
        last_exc: Exception | None = None
        failed_provider = "unknown"

        while queue:
            rank, build = queue.pop(0)
            if rank > 0:
                observability.record_fallback(
                    failed_provider,
                    type(last_exc).__name__ if last_exc else "unknown")
                _emit_resilience("llm.failover", org,
                                 {"from_provider": failed_provider,
                                  "reason": type(last_exc).__name__ if last_exc else "unknown",
                                  "attempt": rank})
            try:
                model, provider, model_id, endpoint = build()  # type: ignore[operator]
            except Exception as exc:
                if rank == 0:
                    raise
                log.warning("skipping broken fallback #%d: %s", rank, type(exc).__name__)
                continue
            bkey = breaker_key(provider, endpoint)
            breaker = get_breaker()
            if rank > 0 and not breaker.allow(org, bkey):
                continue
            self._check_rate_limit(org, provider, eff_tier)

            t0 = time.perf_counter()
            committed = False
            usage = {"input": 0, "output": 0}
            with observability.llm_span(persona, eff_tier) as span:
                if span is not None and rank > 0:
                    with contextlib.suppress(Exception):
                        span.set_attribute("pdlc.llm.fallback_rank", rank)
                try:
                    for chunk in model.stream(messages):
                        u = _usage_from_message(chunk)  # last chunk often carries usage
                        if u["input"] or u["output"]:
                            usage = u
                        text = getattr(chunk, "content", "")
                        if text:
                            committed = True
                            yield text
                except Exception as exc:
                    self._record(span, persona, provider, model_id, eff_tier, usage, t0, ok=False, overrides=overrides)
                    if span is not None:
                        with contextlib.suppress(Exception):
                            span.record_exception(exc)
                    if rank > 0:
                        breaker.record_failure(org, bkey)
                    if committed or classify(exc) != "retriable":
                        raise  # NG1: never failover after the first token
                    last_exc, failed_provider = exc, provider
                    if not fallbacks_loaded:
                        fallbacks_loaded = True
                        queue.extend(enumerate(self._fallbacks(eff_tier), start=1))
                    if not queue:
                        raise
                    continue
                if rank > 0:
                    breaker.record_success(org, bkey)
                self._record(span, persona, provider, model_id, eff_tier, usage, t0, ok=True, overrides=overrides)
                return

    @staticmethod
    def _record(span, persona, provider, model_id, tier, usage, t0, *, ok: bool,
                overrides: dict | None = None) -> None:
        """Stamp GenAI semconv attributes on the span, record OTel metrics, and
        emit the `llm.tokens_spent` clickstream event that feeds the Nexus
        spend rollups. usd is None (UNPRICED, not $0) for unknown models."""
        from ..llm.pricing import estimate_usd

        duration_ms = (time.perf_counter() - t0) * 1000
        usd = estimate_usd(provider, model_id, usage, overrides) if ok else None
        if span is not None:
            with contextlib.suppress(Exception):
                span.set_attribute("gen_ai.system", provider)
                span.set_attribute("gen_ai.request.model", model_id)
                span.set_attribute("gen_ai.usage.input_tokens", usage["input"])
                span.set_attribute("gen_ai.usage.output_tokens", usage["output"])
                if ok and usd is None:
                    span.set_attribute("pdlc.unpriced", True)
                else:
                    span.set_attribute("pdlc.cost_usd", usd or 0.0)
        observability.record_llm(
            persona=persona, provider=provider, model=model_id, tier=tier or _DEFAULT_TIER,
            tokens_in=usage["input"], tokens_out=usage["output"], usd=usd or 0.0,
            duration_ms=duration_ms, ok=ok,
        )
        if ok:
            _emit_spend(persona, provider, model_id, tier or _DEFAULT_TIER, usage, usd)


def _emit_spend(persona: str, provider: str, model_id: str, tier: str,
                usage: dict[str, int], usd: float | None) -> None:
    """Best-effort `llm.tokens_spent` — the event the Nexus token/spend rollups
    pivot on. Attribution comes from the turn's bound thread id
    (org:project:session); outside a turn (or non-UUID ids) it is skipped."""
    try:
        import uuid as _uuid

        from pdlc_graph.llm_port import current_thread

        from ..clickstream.emitter import get_emitter

        thread = current_thread() or ""
        parts = thread.split(":")
        if len(parts) < 2:
            return
        get_emitter().emit(
            "llm.tokens_spent",
            {"org_id": _uuid.UUID(parts[0]), "project_id": _uuid.UUID(parts[1]),
             "thread_id": thread,
             "session_id": parts[2] if len(parts) > 2 else None},
            {"provider": provider, "model_id": model_id, "tier": tier,
             "agent_persona": persona, "tokens_in": usage["input"],
             "tokens_out": usage["output"], "usd_estimate": usd},
            str(_uuid.uuid4()),
        )
    except Exception:  # telemetry must never break a turn
        pass


def _emit_resilience(event_type: str, org: str, payload: dict) -> None:
    """Best-effort clickstream event (llm.failover / llm.rate_limited). Uses the
    nil project UUID like the admin audit events — org-level, not project work."""
    try:
        import uuid as _uuid

        from ..clickstream.emitter import get_emitter

        get_emitter().emit(
            event_type,
            {"org_id": _uuid.UUID(str(org)), "project_id": _uuid.UUID(int=0),
             "actor": "system"},
            payload,
            str(_uuid.uuid4()),
        )
    except Exception:  # telemetry must never break a turn
        pass


def _usage_from_message(msg) -> dict[str, int]:
    """Normalise LangChain usage_metadata across providers → {input, output}."""
    try:
        u = getattr(msg, "usage_metadata", None) or {}
        return {
            "input": int(u.get("input_tokens", 0) or 0),
            "output": int(u.get("output_tokens", 0) or 0),
        }
    except Exception:
        return {"input": 0, "output": 0}


def wire_llm_backend(settings) -> bool:
    """Install the factory-backed completion backend when enabled.

    Returns True if installed, False if the offline stub was left in place.
    Guarded by `settings.wire_llm` so CI / dev stay hermetic.
    """
    if not getattr(settings, "wire_llm", False):
        return False
    try:
        from pdlc_graph.llm_port import set_completion_backend

        # Give the factory a DB engine when Postgres is configured, so per-tenant
        # (org_llm_config) + per-agent (agent_llm_config) overrides take effect.
        db = None
        if getattr(settings, "task_store", "memory") == "postgres":
            from ..db.session import get_sync_engine

            db = get_sync_engine(settings)
        factory = LLMProviderFactory(db=db)
        set_completion_backend(FactoryCompletionBackend(factory, org_id="self-host"))
        _log_egress_report(settings)
        return True
    except Exception as exc:  # never block boot on this
        log.warning("LLM backend wiring failed (%s); using offline stub", exc)
        return False


def _log_egress_report(settings) -> None:
    """Boot-time honesty about which providers honor the egress config
    (PRD-08 FR-5) + loud CA-path validation."""
    proxy = getattr(settings, "egress_proxy_url", None)
    ca = getattr(settings, "egress_ca_bundle", None)
    if not (proxy or ca):
        return
    if ca:
        from pathlib import Path

        if not Path(ca).exists():
            log.error("PDLC_EGRESS_CA_BUNDLE=%s does not exist — every TLS "
                      "verification will fail; fix the path or unset it", ca)
    log.info(
        "egress proxy=%s ca=%s — full: anthropic, openai, azure, "
        "openai_compatible, ollama · partial: bedrock (proxy full; CA via "
        "AWS_CA_BUNDLE), gemini (env fallback) · unsupported: vertex (gRPC — "
        "use network-level egress), CLI providers (inherit process env)",
        proxy or "-", ca or "-",
    )


def wire_token_streaming(settings) -> bool:
    """Install a token publisher that pushes `token` frames onto the thread's bus
    channel as agents generate. Guarded by `settings.stream_tokens` so tests +
    the no-stream path are unchanged. Returns True if installed."""
    if not getattr(settings, "stream_tokens", False):
        return False
    from pdlc_graph.llm_port import set_token_publisher

    from .ports import get_event_bus

    def _publish(thread_id: str, frame: dict) -> None:
        try:
            get_event_bus().publish(f"thread:{thread_id}", frame)
        except Exception:  # streaming must never break a turn
            pass

    set_token_publisher(_publish)
    log.info("token streaming enabled")
    return True
