"""OpenAI Codex CLI (subscription) — `codex exec` non-interactive.

Uses your logged-in ChatGPT plan (sign in with ChatGPT). Single-user self-host only.
`model_id` comes from the tier_map.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from ...config import settings
from .cli import build_cli


def build(cfg, model_id: str) -> BaseChatModel:
    return build_cli(settings.codex_bin, ["exec"], "--model", model_id)
