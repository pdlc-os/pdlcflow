"""Ollama — ChatOllama for air-gapped / local-model deployments.

Primary use cases: air-gapped self-host (no outbound LLM traffic), local dev
without provider keys, cost-sensitive squads using open-weights models.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    from ._net import effective_proxy, merged_headers

    base_url = cfg.endpoint or "http://localhost:11434"
    kwargs: dict = {"model": model_id, "base_url": base_url}
    net = getattr(cfg, "network", None)
    client_kwargs: dict = {}
    proxy = effective_proxy(net, base_url)  # PDLC_EGRESS_NO_PROXY exempts in-cluster hosts
    if proxy:
        client_kwargs["proxy"] = proxy
    if net is not None and net.ca_bundle:
        client_kwargs["verify"] = net.ca_bundle
    headers = merged_headers(net)
    if headers:
        client_kwargs["headers"] = headers
    if client_kwargs:
        kwargs["client_kwargs"] = client_kwargs
    return ChatOllama(**kwargs)
