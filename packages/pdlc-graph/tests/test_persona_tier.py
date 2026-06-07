"""Persona → capability tier wiring.

Each persona declares a provider-neutral tier (opus/sonnet/haiku) in its
soul-spec frontmatter; `complete()` defaults to that tier so every agent runs at
its intended capability level. The engine's tier_map then resolves the tier to a
concrete model for whichever provider is active.
"""

from __future__ import annotations

from pdlc_graph.llm_port import complete, reset_completion_backend
from pdlc_graph.personas import PERSONAS, TIERS, persona_tier


def test_declared_tiers_match_frontmatter():
    # Leads run frontier, specialists balanced, the evaluator cheap.
    assert persona_tier("neo") == "opus"
    assert persona_tier("atlas") == "opus"
    assert persona_tier("echo") == "sonnet"
    assert persona_tier("muse") == "sonnet"
    assert persona_tier("sentinel") == "haiku"


def test_every_persona_has_a_valid_tier():
    for p in PERSONAS:
        assert persona_tier(p) in TIERS


def test_unknown_persona_defaults_to_opus():
    assert persona_tier("nobody") == "opus"


def test_complete_uses_the_persona_tier_by_default():
    reset_completion_backend()  # offline stub echoes the resolved tier
    # Sentinel is haiku, Neo is opus — the stub bakes the tier into its output.
    assert ":haiku:" in complete("sentinel", "evaluate this")
    assert ":opus:" in complete("neo", "design this")
    assert ":sonnet:" in complete("muse", "shape the UX")


def test_explicit_tier_overrides_the_persona_default():
    reset_completion_backend()
    assert ":opus:" in complete("sentinel", "now think hard", tier="opus")
