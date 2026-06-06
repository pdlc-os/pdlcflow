"""Drift / regression eval (deterministic token-overlap vs a golden reference).

Compares the current output to a committed golden reference and scores their
similarity. A drop below threshold == drift (the agent/pipeline changed what it
produces for a fixed input). Used by the golden-set regression suite + CI.

`extra={"reference": <golden text>}`. Similarity = Jaccard over word sets — crude
but deterministic and dependency-free; swap in embeddings/semantic-diff later.
"""

from __future__ import annotations

import re

from ..registry import EvalSpec, register
from ..schema import EvalContext, EvalResult

_WORD = re.compile(r"[a-z0-9]+")
THRESHOLD = 0.85


def _jaccard(a: str, b: str) -> float:
    wa, wb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _run(ctx: EvalContext, spec: EvalSpec) -> EvalResult:
    reference = str(ctx.extra.get("reference", ""))
    score = _jaccard(ctx.output or "", reference)
    return EvalResult(
        eval_id=spec.eval_id, kind=spec.kind, dimension=spec.dimension,
        target=ctx.target, trigger=ctx.trigger, score=score, threshold=spec.threshold,
        passed=score >= spec.threshold, blocking=spec.blocking,
        rationale=f"similarity-to-golden={score:.3f} (threshold {spec.threshold})",
    )


register(EvalSpec(
    eval_id="drift",
    dimension="drift",
    kind="deterministic",
    triggers=frozenset({"regression"}),
    threshold=THRESHOLD,
    blocking=False,
    fn=_run,
    description="Output drift vs a committed golden reference (regression detection).",
))
