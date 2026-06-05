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

    def complete(
        self, persona: str, prompt: str, *, tier: str | None = None, system: str | None = None
    ) -> str:
        model = self._factory.get_model(
            persona=persona,
            tier=tier or _DEFAULT_TIER,  # type: ignore[arg-type]
            tenant=TenantCtx(org_id=self._org_id),
        )
        messages: list = []
        if system:
            messages.append(("system", system))
        messages.append(("human", prompt))
        result = model.invoke(messages)
        return getattr(result, "content", str(result))


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
