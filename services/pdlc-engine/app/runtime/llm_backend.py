"""LLM backend adapter — bridges the engine's provider factory into the graph.

pdlc-graph nodes call `llm_port.complete(persona, prompt)` and never import the
engine. At boot the engine installs a factory-backed implementation so personas
resolve through `LLMProviderFactory` (two-level org/agent config → provider →
model). It is wired ONLY when explicitly enabled, so dev/test keep the
deterministic offline stub (no creds, no network, no model drift).
"""

from __future__ import annotations

import logging

from ..llm.factory import LLMProviderFactory, TenantCtx

log = logging.getLogger("pdlc.runtime.llm")

# Persona → tier follows the soul-spec frontmatter; default opus for the
# product/architecture leads, sonnet otherwise. Kept simple here; the factory's
# tier_map does the model resolution.
_DEFAULT_TIER = "opus"


class FactoryCompletionBackend:
    def __init__(self, factory: LLMProviderFactory, org_id: str) -> None:
        self._factory = factory
        self._org_id = org_id

    def _model(self, persona: str, tier: str | None):
        return self._factory.get_model(
            persona=persona,
            tier=tier or _DEFAULT_TIER,  # type: ignore[arg-type]
            tenant=TenantCtx(org_id=self._org_id),
        )

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
        result = self._model(persona, tier).invoke(self._messages(system, prompt))
        return getattr(result, "content", str(result))

    def stream(
        self, persona: str, prompt: str, *, tier: str | None = None, system: str | None = None
    ):
        """Yield text chunks as the model streams (powers live token streaming)."""
        for chunk in self._model(persona, tier).stream(self._messages(system, prompt)):
            text = getattr(chunk, "content", "")
            if text:
                yield text


def wire_llm_backend(settings) -> bool:
    """Install the factory-backed completion backend when enabled.

    Returns True if installed, False if the offline stub was left in place.
    Guarded by `settings.wire_llm` so CI / dev stay hermetic.
    """
    if not getattr(settings, "wire_llm", False):
        return False
    try:
        from pdlc_graph.llm_port import set_completion_backend

        factory = LLMProviderFactory()
        # org_id is resolved per-request in the full multi-tenant path; for the
        # single-tenant self-host boot we bind the instance default.
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
