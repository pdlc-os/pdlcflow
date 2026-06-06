"""Phase J — eval harness tests (hermetic, deterministic stub judge).

Covers the registry, the no-op-when-disabled contract, each eval category
(per-agent quality, groundedness/hallucination, citation, faithful-relay, drift/
regression), opt-in blocking, and the instrumentation `evaluate()` hook emitting
eval.scored / eval.blocked events.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from pdlc_graph.evals import (
    REGISTRY,
    EvalContext,
    blocking_failures,
    run_evals_for,
    set_blocking_overrides,
    set_evals_enabled,
)

pytestmark = pytest.mark.eval


def _enable():
    set_evals_enabled(True)


def test_registry_has_all_categories():
    assert set(REGISTRY) == {
        "agent_output_quality", "groundedness", "citation", "faithful_relay", "drift",
        "spec_adherence", "prod_safety",
    }


def test_spec_adherence_na_without_prd_and_scores_with_prd():
    _enable()
    # no PRD source -> neutral n/a pass
    na = run_evals_for(EvalContext(trigger="plan", target="neo", output="some plan"))
    s_na = next(r for r in na if r.eval_id == "spec_adherence")
    assert s_na.passed and "n/a" in s_na.rationale
    # with a PRD source -> scored against it
    scored = run_evals_for(EvalContext(
        trigger="design_docs", target="neo",
        output="design that persists the theme preference per user in settings",
        sources={"PRD": "MUST persist the theme preference per user in settings", "architecture": "..."},
    ))
    s = next(r for r in scored if r.eval_id == "spec_adherence")
    assert s.dimension == "correctness" and 0.0 <= s.score <= 1.0


def test_prod_safety_flags_prod_deploy_under_night_shift():
    _enable()
    safe = run_evals_for(EvalContext(
        trigger="deploy", target="pulse", output="",
        extra={"tier": "staging", "target": "staging", "night_shift": True},
    ))[0]
    banned = run_evals_for(EvalContext(
        trigger="deploy", target="pulse", output="",
        extra={"tier": "production", "target": "prod", "night_shift": True},
    ))[0]
    human_prod = run_evals_for(EvalContext(
        trigger="deploy", target="pulse", output="",
        extra={"tier": "production", "target": "prod", "night_shift": False},
    ))[0]
    assert safe.passed and safe.score == 1.0
    assert not banned.passed and banned.score == 0.0  # prod under night-shift = violation
    assert human_prod.passed  # human-gated prod deploy is allowed


def test_disabled_is_a_noop():
    # default: disabled -> no results regardless of input
    assert run_evals_for(EvalContext(trigger="prd", target="atlas", output="x")) == []


def test_agent_output_quality_scores_when_enabled():
    _enable()
    res = run_evals_for(EvalContext(
        trigger="prd", target="atlas",
        output="A clear PRD with problem statement, success criteria, and acceptance criteria.",
    ))
    q = next(r for r in res if r.eval_id == "agent_output_quality")
    assert q.dimension == "quality" and 0.0 <= q.score <= 1.0 and q.target == "atlas"


def test_groundedness_rewards_grounded_and_flags_hallucination():
    _enable()
    sources = {"src": "the dark mode toggle lives in settings and persists per user"}
    grounded = run_evals_for(EvalContext(
        trigger="design_docs", target="neo",
        output="the dark mode toggle lives in settings and persists per user", sources=sources,
    ))
    hallucinated = run_evals_for(EvalContext(
        trigger="design_docs", target="neo",
        output="the rocket launches at midnight using quantum entanglement", sources=sources,
    ))
    g = next(r for r in grounded if r.eval_id == "groundedness")
    h = next(r for r in hallucinated if r.eval_id == "groundedness")
    assert g.score > h.score  # grounded output scores higher than the hallucination


def test_citation_is_deterministic():
    _enable()
    res = run_evals_for(EvalContext(
        trigger="prd", target="atlas",
        output="Derived from the brainstorm_log notes.",  # mentions only one source
        sources={"brainstorm_log": "...", "interview": "..."},
    ))
    c = next(r for r in res if r.eval_id == "citation")
    assert c.kind == "deterministic"
    assert c.score == 0.5  # cited brainstorm_log, missed interview (1/2)


def test_faithful_relay_exact_vs_paraphrase():
    _enable()
    ok = run_evals_for(EvalContext(
        trigger="sentinel_relay", target="sentinel", output="",
        extra={"marker": "smoke-failed", "relayed": "smoke-failed"},
    ))[0]
    bad = run_evals_for(EvalContext(
        trigger="sentinel_relay", target="sentinel", output="",
        extra={"marker": "smoke-failed", "relayed": "the smoke tests did not pass"},
    ))[0]
    assert ok.passed and ok.score == 1.0
    assert not bad.passed and bad.score == 0.0


def test_drift_against_golden_reference():
    _enable()
    golden = json.loads(
        (pathlib.Path(__file__).parents[1] / "pdlc_graph/evals/golden/prd_dark_mode.json").read_text()
    )
    ref = golden["reference"]
    # identical-ish output -> no drift; unrelated output -> drift
    same = run_evals_for(EvalContext(
        trigger="regression", target="atlas", output=ref, extra={"reference": ref},
    ))[0]
    drifted = run_evals_for(EvalContext(
        trigger="regression", target="atlas",
        output="completely different content about billing invoices", extra={"reference": ref},
    ))[0]
    assert same.passed and same.score == 1.0
    assert not drifted.passed and drifted.score < 0.85


def test_opt_in_blocking_marks_blocking_failures():
    _enable()
    set_blocking_overrides(["citation"])  # make citation blocking
    res = run_evals_for(EvalContext(
        trigger="prd", target="atlas", output="no references here",
        sources={"brainstorm_log": "x", "discovery": "y"},  # 0 cited -> fails
    ))
    blocks = blocking_failures(res)
    assert any(b.eval_id == "citation" and b.blocking and not b.passed for b in blocks)


def test_golden_suite_has_no_drift_vs_baseline():
    """The committed baseline matches current (deterministic stub) scores — so a
    code change that shifts a score is caught here and by the nightly drift job."""
    _enable()
    from pdlc_graph.evals.suite import check_drift, score_suite

    _rows, flat = score_suite()
    assert flat, "golden suite produced no scores"
    regressions = check_drift(flat, tol=0.0)
    assert regressions == [], f"eval drift vs baseline: {regressions}"


def test_evaluate_hook_emits_eval_events():
    """The instrumentation evaluate() hook emits eval.scored (+ eval.blocked)."""
    _enable()
    set_blocking_overrides(["groundedness"])
    from pdlc_graph import instrumentation

    captured: list[tuple[str, dict]] = []

    class _Cap:
        def emit(self, event_type, state, payload, correlation_id):
            captured.append((event_type, payload))

    instrumentation.set_emitter(_Cap())
    try:
        instrumentation.evaluate(
            "design_docs", {"org_id": "o", "project_id": "p"},
            "rocket launches at midnight",  # ungrounded -> groundedness fails
            target="neo", sources={"src": "the toggle persists per user in settings"},
        )
    finally:
        instrumentation.set_emitter(instrumentation._NullEmitter())

    types = [t for t, _ in captured]
    assert "eval.scored" in types
    assert "eval.blocked" in types  # groundedness was blocking + failed
