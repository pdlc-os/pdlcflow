"""Azure OpenAI — AzureChatOpenAI for GPT deployments.

Claude-via-Azure-AI-Foundry is a stub until the LangChain integration is
generally available; the resolver will pick OpenAI direct or Bedrock as a
fallback when the org config requests Azure Claude.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_openai import AzureChatOpenAI
    return AzureChatOpenAI(
        deployment_name=model_id,
        azure_endpoint=cfg.endpoint or "https://example.openai.azure.com",
        api_key=cfg.secret_value or "",
        api_version="2024-10-21",
    )
