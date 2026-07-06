"""Generic OpenAI-protocol provider — relay gateways (OpenRouter, DeepSeek,
Kimi, GLM, SiliconFlow, …) and self-hosted servers (LiteLLM, vLLM, Ollama's
/v1). The tenant supplies the base_url; there is deliberately NO env-var
fallback for the key (which env var would it be, for an arbitrary gateway?) —
keyless is valid for local servers.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    if not cfg.endpoint:
        raise ValueError(
            "openai_compatible requires an endpoint (the gateway/server base_url)"
        )
    return ChatOpenAI(
        model=model_id,
        base_url=cfg.endpoint,
        # Local vLLM/LiteLLM without auth still need a non-empty key kwarg.
        api_key=cfg.secret_value or "not-needed",
    )
