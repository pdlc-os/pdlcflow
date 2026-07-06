"""Google Gemini direct — ChatGoogleGenerativeAI via langchain-google-genai.

API key precedence: the per-tenant/agent `secret_value` if set, otherwise the
SDK's own `GOOGLE_API_KEY` environment variable.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build(cfg, model_id: str) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    kwargs: dict = {"model": model_id}
    if cfg.secret_value:
        kwargs["google_api_key"] = cfg.secret_value  # else GOOGLE_API_KEY from env
    # Egress (partial): several google-genai versions only honor ambient env.
    # Set process-scoped vars IFF the operator configured egress AND the var is
    # unset — never overwrite operator-provided env. extra_headers unsupported.
    import os

    net = getattr(cfg, "network", None)
    if net is not None:
        if net.proxy_url and not os.environ.get("HTTPS_PROXY"):
            os.environ["HTTPS_PROXY"] = net.proxy_url
        if net.ca_bundle and not os.environ.get("SSL_CERT_FILE"):
            os.environ["SSL_CERT_FILE"] = net.ca_bundle
    return ChatGoogleGenerativeAI(**kwargs)
