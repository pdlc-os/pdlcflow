"""Persona → capability tier wiring.

Each persona declares a provider-neutral tier (premium/balanced/economy) in its
soul-spec frontmatter; `complete()` defaults to that tier so every agent runs at
its intended capability level. The engine's tier_map then resolves the tier to a
concrete model for whichever provider is active.
"""

from __future__ import annotations

from pdlc_graph.llm_port import complete, reset_completion_backend
from pdlc_graph.personas import PERSONAS, TIERS, persona_tier


def test_declared_tiers_match_frontmatter():
    # Leads run premium, specialists balanced, the evaluator economy.
    assert persona_tier("neo") == "premium"
    assert persona_tier("atlas") == "premium"
    assert persona_tier("echo") == "balanced"
    assert persona_tier("muse") == "balanced"
    assert persona_tier("sentinel") == "economy"


def test_every_persona_has_a_valid_tier():
    for p in PERSONAS:
        assert persona_tier(p) in TIERS


def test_unknown_persona_defaults_to_premium():
    assert persona_tier("nobody") == "premium"


def test_complete_uses_the_persona_tier_by_default():
    reset_completion_backend()  # offline stub echoes the resolved tier
    assert ":economy:" in complete("sentinel", "evaluate this")
    assert ":premium:" in complete("neo", "design this")
    assert ":balanced:" in complete("muse", "shape the UX")


def test_explicit_tier_overrides_the_persona_default():
    reset_completion_backend()
    assert ":premium:" in complete("sentinel", "now think hard", tier="premium")
