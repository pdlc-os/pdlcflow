"""OpenAI direct — ChatOpenAI for GPT models.

API key precedence: the per-tenant/agent `secret_value` if set, otherwise the
SDK's own `OPENAI_API_KEY` environment variable.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    kwargs: dict = {"model": model_id}
    if cfg.secret_value:
        kwargs["api_key"] = cfg.secret_value  # else OPENAI_API_KEY from env
    return ChatOpenAI(**kwargs)
