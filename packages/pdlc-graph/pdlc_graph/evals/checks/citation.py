"""Citation / faithful-relay evals (deterministic, no LLM).

`citation`      — does the output reference the source artifacts it derives from?
                  (every named source should appear/be cited in the output).
`faithful_relay`— for Sentinel verdicts: the relayed reason must equal the marker
                  verbatim (no paraphrase). Enforces the audit-trail contract.
"""

from __future__ import annotations

from ..registry import EvalSpec, register
from ..schema import EvalContext, EvalResult


def _citation(ctx: EvalContext, spec: EvalSpec) -> EvalResult:
    names = list(ctx.sources.keys())
    if not names:
        return EvalResult(
            eval_id=spec.eval_id, kind=spec.kind, dimension=spec.dimension,
            target=ctx.target, trigger=ctx.trigger, score=1.0, threshold=spec.threshold,
            passed=True, blocking=spec.blocking, rationale="no sources to cite",
        )
    low = (ctx.output or "").lower()
    cited = [n for n in names if n.lower() in low]
    score = len(cited) / len(names)
    missing = [n for n in names if n not in cited]
    return EvalResult(
        eval_id=spec.eval_id, kind=spec.kind, dimension=spec.dimension,
        target=ctx.target, trigger=ctx.trigger, score=score, threshold=spec.threshold,
        passed=score >= spec.threshold, blocking=spec.blocking,
        rationale=f"cited {len(cited)}/{len(names)} sources" + (f"; missing {missing}" if missing else ""),
        refs=cited,
    )


def _faithful_relay(ctx: EvalContext, spec: EvalSpec) -> EvalResult:
    """Sentinel relay fidelity: extra={"marker": <verbatim>, "relayed": <as-relayed>}."""
    marker = str(ctx.extra.get("marker", ""))
    relayed = str(ctx.extra.get("relayed", ""))
    exact = marker.strip() == relayed.strip() and marker != ""
    return EvalResult(
        eval_id=spec.eval_id, kind=spec.kind, dimension=spec.dimension,
        target=ctx.target, trigger=ctx.trigger, score=1.0 if exact else 0.0,
        threshold=spec.threshold, passed=exact, blocking=spec.blocking,
        rationale="verbatim relay" if exact else f"paraphrase detected: marker={marker!r} relayed={relayed!r}",
    )


register(EvalSpec(
    eval_id="citation",
    dimension="citation",
    kind="deterministic",
    triggers=frozenset({"prd", "design_docs", "plan"}),
    threshold=0.5,
    blocking=False,
    fn=_citation,
    description="Does the output cite/reference the source artifacts it was built from?",
))

register(EvalSpec(
    eval_id="faithful_relay",
    dimension="faithful_relay",
    kind="deterministic",
    triggers=frozenset({"sentinel_relay"}),
    threshold=1.0,  # must be exact
    blocking=False,
    fn=_faithful_relay,
    description="Sentinel relays the evaluator's reason verbatim — no paraphrase (audit integrity).",
))
