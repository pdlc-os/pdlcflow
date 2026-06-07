"""Google Vertex AI — ChatAnthropicVertex (Claude on Vertex).

Project/region precedence: per-tenant config (`endpoint` as "project:..."; `region`)
→ env (`GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_REGION`). Auth uses Google ADC
(`GOOGLE_APPLICATION_CREDENTIALS` or workload identity).
"""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_google_vertexai.model_garden import ChatAnthropicVertex

    project = (
        (cfg.endpoint or "").split(":")[0]
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
        or "your-gcp-project"
    )
    location = cfg.region or os.environ.get("GOOGLE_CLOUD_REGION") or "us-east5"
    return ChatAnthropicVertex(model_name=model_id, project=project, location=location)
