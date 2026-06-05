"""Reads persona soul-spec markdown files.

The 10 persona files (atlas.md, bolt.md, echo.md, friday.md, jarvis.md,
muse.md, neo.md, phantom.md, pulse.md, sentinel.md) are verbatim copies
of upstream pdlc/agents/*.md and serve as the system prompt for each
persona's create_react_agent.

Sentinel is loaded for completeness but never invoked as an LLM — the
deterministic Python evaluator in pdlc_graph/sentinel/evaluator.py is
the real implementation. See agents/sentinel.md "Operating Precondition".
"""

from __future__ import annotations

from pathlib import Path

PERSONAS: tuple[str, ...] = (
    "atlas", "bolt", "echo", "friday", "jarvis",
    "muse", "neo", "phantom", "pulse", "sentinel",
)

_PERSONA_DIR = Path(__file__).parent


def load_persona_spec(name: str) -> str:
    if name not in PERSONAS:
        raise KeyError(f"unknown persona {name!r}; valid: {PERSONAS}")
    return (_PERSONA_DIR / f"{name}.md").read_text(encoding="utf-8")
