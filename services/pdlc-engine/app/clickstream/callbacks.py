"""LangChain callback handlers that forward to the clickstream emitter."""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler

from ..llm.pricing import estimate_usd
from .emitter import get_emitter


class LLMTokenTallyCallback(BaseCallbackHandler):
    """Fires `llm.tokens_spent` per LLM completion. Provider-agnostic."""

    def __init__(self, state: dict, provider: str, model_id: str,
                 tier: str, agent_persona: str):
        self._state = state
        self._provider = provider
        self._model_id = model_id
        self._tier = tier
        self._persona = agent_persona

    def on_llm_end(self, response: Any, **_kw: Any) -> None:
        usage = _extract_usage(response)
        get_emitter().emit(
            "llm.tokens_spent",
            self._state,
            {
                "provider": self._provider,
                "model_id": self._model_id,
                "tier": self._tier,
                "agent_persona": self._persona,
                "tokens_in": usage["input"],
                "tokens_out": usage["output"],
                "usd_estimate": estimate_usd(self._provider, self._model_id, usage),
            },
            self._state.get("correlation_id", ""),
        )


def _extract_usage(response: Any) -> dict[str, int]:
    """Normalize usage across providers. Each LangChain integration exposes
    usage_metadata in `response.llm_output` or message metadata; fall back to 0
    when the provider doesn't report (e.g. some streaming paths)."""
    try:
        meta = response.llm_output or {}
        u = meta.get("usage") or meta.get("token_usage") or {}
        return {
            "input": int(u.get("input_tokens", u.get("prompt_tokens", 0))),
            "output": int(u.get("output_tokens", u.get("completion_tokens", 0))),
        }
    except Exception:
        return {"input": 0, "output": 0}
