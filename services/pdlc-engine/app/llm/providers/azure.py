"""Azure OpenAI — AzureChatOpenAI for GPT deployments.

Claude-via-Azure-AI-Foundry is a stub until the LangChain integration is
generally available; the resolver will pick OpenAI direct or Bedrock as a
fallback when the org config requests Azure Claude.

Credentials: the per-tenant/agent `secret_value` + `endpoint` if set, otherwise
the SDK's `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` environment variables.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_openai import AzureChatOpenAI

    kwargs: dict = {"deployment_name": model_id, "api_version": "2024-10-21"}
    if cfg.endpoint:
        kwargs["azure_endpoint"] = cfg.endpoint  # else AZURE_OPENAI_ENDPOINT from env
    if cfg.secret_value:
        kwargs["api_key"] = cfg.secret_value  # else AZURE_OPENAI_API_KEY from env
    from ._net import httpx_clients, merged_headers

    net = getattr(cfg, "network", None)
    sync_c, async_c = httpx_clients(net, cfg.endpoint)
    if sync_c is not None:
        kwargs["http_client"] = sync_c
        kwargs["http_async_client"] = async_c
    headers = merged_headers(net)
    if headers:
        kwargs["default_headers"] = headers
    return AzureChatOpenAI(**kwargs)
