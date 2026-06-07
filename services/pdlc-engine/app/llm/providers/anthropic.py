"""Anthropic direct — ChatAnthropic via langchain-anthropic.

API key precedence: the per-tenant/agent `secret_value` (from org config) if set,
otherwise the SDK's own `ANTHROPIC_API_KEY` environment variable.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    kwargs: dict = {"model": model_id}
    if cfg.secret_value:
        kwargs["api_key"] = cfg.secret_value  # else ANTHROPIC_API_KEY from env
    return ChatAnthropic(**kwargs)
