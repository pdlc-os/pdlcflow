"""Anthropic direct — ChatAnthropic via langchain-anthropic."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=model_id, api_key=cfg.secret_value or "")
