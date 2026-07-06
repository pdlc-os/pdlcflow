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
    from ._net import httpx_clients, merged_headers

    kwargs: dict = {
        "model": model_id,
        "base_url": cfg.endpoint,
        # Local vLLM/LiteLLM without auth still need a non-empty key kwarg.
        "api_key": cfg.secret_value or "not-needed",
    }
    net = getattr(cfg, "network", None)
    sync_c, async_c = httpx_clients(net, cfg.endpoint)
    if sync_c is not None:
        kwargs["http_client"] = sync_c
        kwargs["http_async_client"] = async_c
    headers = merged_headers(net)
    if headers:
        kwargs["default_headers"] = headers
    return ChatOpenAI(**kwargs)
