"""Per-agent output-quality eval (LLM-as-judge against a role rubric)."""

from __future__ import annotations

from ..judge_port import judge
from ..registry import EvalSpec, register
from ..rubrics import agent_quality_rubric
from ..schema import EvalContext, EvalResult

THRESHOLD = 0.6


def _run(ctx: EvalContext, spec: EvalSpec) -> EvalResult:
    rubric = agent_quality_rubric(ctx.target)
    v = judge(rubric=rubric, dimension="quality", output=ctx.output, sources=ctx.sources)
    score = float(v["score"])
    return EvalResult(
        eval_id=spec.eval_id, kind=spec.kind, dimension=spec.dimension,
        target=ctx.target, trigger=ctx.trigger, score=score, threshold=spec.threshold,
        passed=score >= spec.threshold, blocking=spec.blocking, rationale=v["rationale"],
    )


register(EvalSpec(
    eval_id="agent_output_quality",
    dimension="quality",
    kind="llm_judge",
    triggers=frozenset({"prd", "design_docs", "plan", "review", "episode"}),
    threshold=THRESHOLD,
    blocking=False,  # measure-only by default
    fn=_run,
    description="Per-agent output quality scored against the persona's role rubric.",
))
