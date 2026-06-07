"""Google Gemini direct — ChatGoogleGenerativeAI via langchain-google-genai.

API key precedence: the per-tenant/agent `secret_value` if set, otherwise the
SDK's own `GOOGLE_API_KEY` environment variable.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    kwargs: dict = {"model": model_id}
    if cfg.secret_value:
        kwargs["google_api_key"] = cfg.secret_value  # else GOOGLE_API_KEY from env
    return ChatGoogleGenerativeAI(**kwargs)
