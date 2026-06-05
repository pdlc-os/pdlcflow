"""AWS Bedrock — ChatBedrockConverse via langchain-aws."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_aws import ChatBedrockConverse
    return ChatBedrockConverse(model=model_id, region_name=cfg.region or "us-east-1")
