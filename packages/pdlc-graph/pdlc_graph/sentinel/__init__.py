"""Sentinel — deterministic Python evaluator for /night-shift verdicts.

Sentinel's upstream persona (agents/sentinel.md) is "paranoid faithfulness;
never paraphrases; produce one JSON object per fire." A pure function matches
that identity better than any LLM call would, and it removes the Agent Teams
mode dependency that the upstream Stop-hook-as-agent implementation requires.
"""

from .evaluator import evaluate

__all__ = ["evaluate"]
