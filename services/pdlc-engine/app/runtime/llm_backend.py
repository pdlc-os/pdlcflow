"""LLM backend adapter — bridges the engine's provider factory into the graph.

pdlc-graph nodes call `llm_port.complete(persona, prompt)` and never import the
engine. At boot the engine installs a factory-backed implementation so personas
resolve through `LLMProviderFactory` (two-level org/agent config → provider →
model). It is wired ONLY when explicitly enabled, so dev/test keep the
deterministic offline stub (no creds, no network, no model drift).
"""

from __future__ import annotations

import contextlib
import logging
import time

from .. import observability
from ..llm.factory import LLMProviderFactory, TenantCtx

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
        model, provider, model_id = self._resolve(persona, tier)
        t0 = time.perf_counter()
        # LLM span — the leaf of the trace tree, with GenAI semconv + cost. No-op
        # unless observability is wired.
        with observability.llm_span(persona, eff_tier) as span:
            try:
                result = model.invoke(self._messages(system, prompt))
            except Exception:
                self._record(span, persona, provider, model_id, eff_tier,
                             {"input": 0, "output": 0}, t0, ok=False)
                raise
            usage = _usage_from_message(result)
            self._record(span, persona, provider, model_id, eff_tier, usage, t0, ok=True)
            return getattr(result, "content", str(result))

    def stream(
        self, persona: str, prompt: str, *, tier: str | None = None, system: str | None = None
    ):
        """Yield text chunks as the model streams (powers live token streaming)."""
        eff_tier = tier or _DEFAULT_TIER
        model, provider, model_id = self._resolve(persona, tier)
        t0 = time.perf_counter()
        with observability.llm_span(persona, eff_tier) as span:
            usage = {"input": 0, "output": 0}
            try:
                for chunk in model.stream(self._messages(system, prompt)):
                    u = _usage_from_message(chunk)  # last chunk often carries usage
                    if u["input"] or u["output"]:
                        usage = u
                    text = getattr(chunk, "content", "")
                    if text:
                        yield text
            except Exception:
                self._record(span, persona, provider, model_id, eff_tier, usage, t0, ok=False)
                raise
            self._record(span, persona, provider, model_id, eff_tier, usage, t0, ok=True)

    @staticmethod
    def _record(span, persona, provider, model_id, tier, usage, t0, *, ok: bool) -> None:
        """Stamp GenAI semconv attributes on the span + record OTel metrics."""
        from ..llm.pricing import estimate_usd

        duration_ms = (time.perf_counter() - t0) * 1000
        usd = estimate_usd(provider, model_id, usage) if ok else 0.0
        if span is not None:
            with contextlib.suppress(Exception):
                span.set_attribute("gen_ai.system", provider)
                span.set_attribute("gen_ai.request.model", model_id)
                span.set_attribute("gen_ai.usage.input_tokens", usage["input"])
                span.set_attribute("gen_ai.usage.output_tokens", usage["output"])
                span.set_attribute("pdlc.cost_usd", usd)
        observability.record_llm(
            persona=persona, provider=provider, model=model_id, tier=tier or _DEFAULT_TIER,
            tokens_in=usage["input"], tokens_out=usage["output"], usd=usd,
            duration_ms=duration_ms, ok=ok,
        )


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
        return True
    except Exception as exc:  # never block boot on this
        log.warning("LLM backend wiring failed (%s); using offline stub", exc)
        return False


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
