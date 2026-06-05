"""OpenAI direct — ChatOpenAI for GPT-4o / GPT-4 Turbo / o1."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model_id, api_key=cfg.secret_value or "")
