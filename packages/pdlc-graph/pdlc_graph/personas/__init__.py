"""Persona soul-spec loader.

Soul-spec markdowns are verbatim copies from upstream pdlc/agents/*.md.
They are the system prompt for each persona's create_react_agent factory.
"""

from .loader import PERSONAS, load_persona_spec

__all__ = ["PERSONAS", "load_persona_spec"]
