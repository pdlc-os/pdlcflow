"""Spec-adherence eval — does the design/plan satisfy the PRD? (LLM-as-judge).

Compares the design or plan output against the PRD's requirements + acceptance
criteria (supplied as the `PRD` source). Catches scope drift and unaddressed
MUST requirements — a downstream-correctness check distinct from groundedness
(which only asks whether claims are *supported*, not whether the spec is *met*).
"""

from __future__ import annotations

from ..judge_port import judge
from ..registry import EvalSpec, register
from ..rubrics import SPEC_ADHERENCE_RUBRIC
from ..schema import EvalContext, EvalResult

THRESHOLD = 0.7


def _run(ctx: EvalContext, spec: EvalSpec) -> EvalResult:
    prd = ctx.sources.get("PRD")
    if not prd:
        # No PRD to check against — neutral, non-failing (don't penalize a step
        # that legitimately ran without an upstream PRD).
        return EvalResult(
            eval_id=spec.eval_id, kind=spec.kind, dimension=spec.dimension,
            target=ctx.target, trigger=ctx.trigger, score=1.0, threshold=spec.threshold,
            passed=True, blocking=spec.blocking, rationale="no PRD source; spec-adherence n/a",
        )
    v = judge(rubric=SPEC_ADHERENCE_RUBRIC, dimension="correctness", output=ctx.output, sources={"PRD": prd})
    score = float(v["score"])
    return EvalResult(
        eval_id=spec.eval_id, kind=spec.kind, dimension=spec.dimension,
        target=ctx.target, trigger=ctx.trigger, score=score, threshold=spec.threshold,
        passed=score >= spec.threshold, blocking=spec.blocking, rationale=v["rationale"], refs=["PRD"],
    )


register(EvalSpec(
    eval_id="spec_adherence",
    dimension="correctness",
    kind="llm_judge",
    triggers=frozenset({"design_docs", "plan"}),
    threshold=THRESHOLD,
    blocking=False,
    fn=_run,
    description="Does the design/plan satisfy every PRD requirement + acceptance criterion?",
))
