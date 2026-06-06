"""Eval runner — run all evals registered for a trigger over one output.

Strict no-op when evals are disabled (the default), so the hermetic suite and
production are untouched until `PDLC_RUN_EVALS` is set. A failing eval never
raises into the graph; it is captured and returned as a result.
"""

from __future__ import annotations

import logging

from . import checks as _checks  # noqa: F401  (ensures evals are registered)
from .registry import evals_enabled, evals_for_trigger, is_blocking
from .schema import EvalContext, EvalResult

log = logging.getLogger("pdlc.evals")


def run_evals_for(ctx: EvalContext) -> list[EvalResult]:
    """Run every eval registered for `ctx.trigger`. Returns [] when disabled."""
    if not evals_enabled():
        return []
    results: list[EvalResult] = []
    for spec in evals_for_trigger(ctx.trigger):
        try:
            res = spec.fn(ctx, spec)
            # apply runtime blocking posture (spec default OR config override)
            res.blocking = is_blocking(spec)
            results.append(res)
        except Exception as exc:  # an eval must never break the graph
            log.warning("eval %s failed on trigger=%s: %s", spec.eval_id, ctx.trigger, exc)
    return results


def blocking_failures(results: list[EvalResult]) -> list[EvalResult]:
    """The subset that should block a gate (blocking + failed)."""
    return [r for r in results if r.blocking and not r.passed]
