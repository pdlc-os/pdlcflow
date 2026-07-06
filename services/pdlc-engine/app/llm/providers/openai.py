"""OpenAI direct — ChatOpenAI for GPT models.

API key precedence: the per-tenant/agent `secret_value` if set, otherwise the
SDK's own `OPENAI_API_KEY` environment variable.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    from ._net import httpx_clients, merged_headers

    kwargs: dict = {"model": model_id}
    if cfg.secret_value:
        kwargs["api_key"] = cfg.secret_value  # else OPENAI_API_KEY from env
    net = getattr(cfg, "network", None)
    sync_c, async_c = httpx_clients(net)
    if sync_c is not None:
        kwargs["http_client"] = sync_c
        kwargs["http_async_client"] = async_c
    headers = merged_headers(net)
    if headers:
        kwargs["default_headers"] = headers
    return ChatOpenAI(**kwargs)
