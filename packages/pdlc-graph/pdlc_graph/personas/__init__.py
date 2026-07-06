"""Persona soul-spec loader.

Soul-spec markdowns are verbatim copies from upstream pdlc/agents/*.md.
They are the system prompt for each persona's create_react_agent factory.
"""

from .loader import (
    PERSONAS,
    TIERS,
    load_persona_spec,
    persona_tier,
    reset_prompt_resolver,
    resolve_persona_prompt,
    set_prompt_resolver,
)

__all__ = [
    "PERSONAS",
    "TIERS",
    "load_persona_spec",
    "persona_tier",
    "reset_prompt_resolver",
    "resolve_persona_prompt",
    "set_prompt_resolver",
]
