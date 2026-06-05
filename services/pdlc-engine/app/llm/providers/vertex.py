"""Google Vertex AI — ChatAnthropicVertex (Claude on Vertex)."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_google_vertexai.model_garden import ChatAnthropicVertex
    project = (cfg.endpoint or "").split(":")[0] or "your-gcp-project"
    return ChatAnthropicVertex(
        model_name=model_id,
        project=project,
        location=cfg.region or "us-east5",
    )
