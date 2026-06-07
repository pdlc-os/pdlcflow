"""Smoke tests for meta-graph routing."""

import pytest


@pytest.mark.parametrize(
    "phase,expected_node",
    [
        ("Initialization", "init"),
        ("Inception", "brainstorm"),
        ("Construction", "build"),
        ("Operation", "ship"),
    ],
)
def test_meta_router_dispatches_by_phase(phase, expected_node):
    from pdlc_graph.graphs.meta import _route
    assert _route({"phase": phase}) == expected_node


def test_meta_router_prefers_night_shift_when_active():
    from pdlc_graph.graphs.meta import _route
    assert _route({"phase": "Construction", "night_shift_active": True}) == "night_shift"


def test_meta_router_defaults_to_utility_on_unknown_phase():
    from pdlc_graph.graphs.meta import _route
    assert _route({"phase": "Whatever"}) == "utility"


def test_sentinel_evaluator_abort_signal():
    from pdlc_graph.sentinel.evaluator import evaluate
    v = evaluate({}, "stuff ns-abort:smoke-failed more stuff")
    assert v == {"ok": False, "verdict": "abort", "reason": "smoke-failed"}


def test_sentinel_evaluator_complete_signal():
    from pdlc_graph.sentinel.evaluator import evaluate
    v = evaluate({}, "ns-progress:build-done\nns-progress:ship-done\nns-progress:complete")
    assert v == {"ok": True, "verdict": "complete"}


def test_sentinel_evaluator_continue_default():
    from pdlc_graph.sentinel.evaluator import evaluate
    v = evaluate({}, "ns-progress:build-done")
    assert v == {"ok": True, "verdict": "continue"}


def test_personas_loadable():
    from pdlc_graph.personas import PERSONAS, load_persona_spec
    assert len(PERSONAS) == 10
    for p in PERSONAS:
        spec = load_persona_spec(p)
        assert spec.startswith("---")  # frontmatter
        assert "tier:" in spec  # tier declaration
