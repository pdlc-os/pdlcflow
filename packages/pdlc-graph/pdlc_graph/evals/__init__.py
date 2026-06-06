"""pdlcflow eval framework (Phase J).

A small, extensible harness that scores agent output at major steps and emits
`eval.scored` / `eval.blocked` events into the clickstream. Evals are a strict
no-op until enabled (`set_evals_enabled(True)`, wired from `PDLC_RUN_EVALS`), and
blocking is opt-in per eval (measure-only by default).

Public surface:
    run_evals_for(EvalContext) -> [EvalResult]      # run the evals for a trigger
    EvalContext, EvalResult, EvalSpec               # core types
    REGISTRY, register, evals_for_trigger           # the registry
    set_evals_enabled / set_blocking_overrides      # runtime config (engine boot)
    set_judge_backend / reset_judge_backend         # the LLM-as-judge seam
"""

from __future__ import annotations

from .judge_port import is_stubbed, judge, reset_judge_backend, set_judge_backend
from .registry import (
    REGISTRY,
    EvalSpec,
    evals_enabled,
    evals_for_trigger,
    register,
    reset_eval_config,
    set_blocking_overrides,
    set_evals_enabled,
)
from .runner import blocking_failures, run_evals_for
from .schema import EvalContext, EvalResult

__all__ = [
    "REGISTRY",
    "EvalContext",
    "EvalResult",
    "EvalSpec",
    "blocking_failures",
    "evals_enabled",
    "evals_for_trigger",
    "is_stubbed",
    "judge",
    "register",
    "reset_eval_config",
    "reset_judge_backend",
    "run_evals_for",
    "set_blocking_overrides",
    "set_evals_enabled",
    "set_judge_backend",
]
