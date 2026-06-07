"""Google Gemini CLI (subscription) — `gemini` non-interactive prompt on stdin.

Uses your logged-in Google account. Single-user self-host only.
`model_id` comes from the tier_map.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from ...config import settings
from .cli import build_cli


def build(cfg, model_id: str) -> BaseChatModel:
    return build_cli(settings.gemini_cli_bin, [], "-m", model_id)
