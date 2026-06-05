"""Google Gemini direct — ChatGoogleGenerativeAI via langchain-google-genai."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=cfg.secret_value or "",
    )
