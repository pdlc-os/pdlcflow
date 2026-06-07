"""Claude Code CLI (subscription) — `claude -p` in print mode.

Uses your logged-in Claude Pro/Max subscription. Single-user self-host only.
`model_id` comes from the tier_map (opus / sonnet / haiku aliases).
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from ...config import settings
from .cli import build_cli


def build(cfg, model_id: str) -> BaseChatModel:
    return build_cli(settings.claude_code_bin, ["-p"], "--model", model_id)
