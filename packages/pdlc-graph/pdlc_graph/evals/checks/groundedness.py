"""Groundedness / faithfulness / hallucination eval (LLM-as-judge vs sources).

Scores whether the output's claims are supported by the provided source
artifacts. Low score == likely hallucination. Defaults to blocking-capable
(opt-in) because an ungrounded PRD/design propagates downstream.
"""

from __future__ import annotations

from ..judge_port import judge
from ..registry import EvalSpec, register
from ..rubrics import GROUNDEDNESS_RUBRIC
from ..schema import EvalContext, EvalResult

THRESHOLD = 0.7


def _run(ctx: EvalContext, spec: EvalSpec) -> EvalResult:
    if not ctx.sources:
        # Nothing to ground against — report a neutral, non-failing result so we
        # never penalize a step that legitimately has no prior artifact.
        return EvalResult(
            eval_id=spec.eval_id, kind=spec.kind, dimension=spec.dimension,
            target=ctx.target, trigger=ctx.trigger, score=1.0, threshold=spec.threshold,
            passed=True, blocking=spec.blocking, rationale="no sources supplied; groundedness n/a",
        )
    v = judge(rubric=GROUNDEDNESS_RUBRIC, dimension="groundedness", output=ctx.output, sources=ctx.sources)
    score = float(v["score"])
    return EvalResult(
        eval_id=spec.eval_id, kind=spec.kind, dimension=spec.dimension,
        target=ctx.target, trigger=ctx.trigger, score=score, threshold=spec.threshold,
        passed=score >= spec.threshold, blocking=spec.blocking, rationale=v["rationale"],
        refs=list(ctx.sources.keys()),
    )


register(EvalSpec(
    eval_id="groundedness",
    dimension="groundedness",
    kind="llm_judge",
    triggers=frozenset({"prd", "design_docs", "plan", "review"}),
    threshold=THRESHOLD,
    blocking=False,  # opt-in blocking via PDLC_EVAL_BLOCKING
    fn=_run,
    description="Are the output's claims supported by the source artifacts (anti-hallucination)?",
))
