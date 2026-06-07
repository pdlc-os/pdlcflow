"""Reads persona soul-spec markdown files.

The 9 LLM persona files (atlas.md, bolt.md, echo.md, friday.md, jarvis.md,
muse.md, neo.md, phantom.md, pulse.md) are adapted from upstream pdlc/agents/*.md
and serve as the system prompt for each persona's create_react_agent.

Sentinel is loaded for completeness but never invoked as an LLM — the
deterministic Python evaluator in pdlc_graph/sentinel/evaluator.py is
the real implementation. sentinel.md is its contract/character spec
(rewritten for pdlcflow — no Claude Code / JS-hook mechanics).
"""

from __future__ import annotations

import functools
from pathlib import Path

PERSONAS: tuple[str, ...] = (
    "atlas", "bolt", "echo", "friday", "jarvis",
    "muse", "neo", "phantom", "pulse", "sentinel",
)

# Capability tiers a persona may declare in its soul-spec frontmatter. The engine's
# tier_map turns the tier into a concrete model per provider (opus → frontier,
# sonnet → general-purpose, haiku → cheap/fast).
TIERS: tuple[str, ...] = ("opus", "sonnet", "haiku")
_DEFAULT_TIER = "opus"

_PERSONA_DIR = Path(__file__).parent


def load_persona_spec(name: str) -> str:
    if name not in PERSONAS:
        raise KeyError(f"unknown persona {name!r}; valid: {PERSONAS}")
    return (_PERSONA_DIR / f"{name}.md").read_text(encoding="utf-8")


@functools.cache
def persona_tier(name: str) -> str:
    """The capability tier a persona declares (`model: opus|sonnet|haiku` in its
    soul-spec frontmatter). Defaults to `opus` if the persona/field is missing or
    invalid. This is the canonical, provider-neutral tier — the engine maps it to
    a concrete model for the active provider."""
    try:
        spec = load_persona_spec(name)
    except KeyError:
        return _DEFAULT_TIER
    lines = spec.splitlines()
    if not lines or lines[0].strip() != "---":
        return _DEFAULT_TIER
    for line in lines[1:]:
        if line.strip() == "---":  # end of frontmatter
            break
        if line.strip().startswith("model:"):
            tier = line.split(":", 1)[1].strip()
            return tier if tier in TIERS else _DEFAULT_TIER
    return _DEFAULT_TIER
