"""AWS Bedrock — ChatBedrockConverse via langchain-aws."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_aws import ChatBedrockConverse

    kwargs: dict = {"model": model_id, "region_name": cfg.region or "us-east-1"}
    net = getattr(cfg, "network", None)
    if net is not None and net.proxy_url:
        from botocore.config import Config

        kwargs["config"] = Config(
            proxies={"http": net.proxy_url, "https": net.proxy_url})
    # CA bundle: botocore reads AWS_CA_BUNDLE — documented as partial in the
    # egress matrix; extra_headers unsupported (signed requests).
    return ChatBedrockConverse(**kwargs)
