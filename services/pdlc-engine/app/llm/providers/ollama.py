"""Ollama — ChatOllama for air-gapped / local-model deployments.

Primary use cases: air-gapped self-host (no outbound LLM traffic), local dev
without provider keys, cost-sensitive squads using open-weights models.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_ollama import ChatOllama
    return ChatOllama(model=model_id, base_url=cfg.endpoint or "http://localhost:11434")
