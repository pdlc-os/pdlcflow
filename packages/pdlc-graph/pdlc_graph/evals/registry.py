"""Eval registry — which evals run, when, and with what threshold.

An `EvalSpec` binds an eval id to: the dimension it measures, the triggers
(steps) it fires on, a default pass threshold, whether it is blocking, and the
check function. Concrete evals register themselves on import (see `checks/`).

Enablement + blocking are runtime-configurable so the harness is a strict no-op
unless turned on (keeps the hermetic suite untouched), and blocking is opt-in
per the agreed posture (measure-only by default).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .schema import EvalContext, EvalResult


@dataclass(frozen=True)
class EvalSpec:
    eval_id: str
    dimension: str
    kind: str  # "llm_judge" | "deterministic"
    triggers: frozenset[str]
    threshold: float
    blocking: bool  # default blocking posture (can be overridden at runtime)
    fn: Callable[[EvalContext, EvalSpec], EvalResult]
    description: str = ""


REGISTRY: dict[str, EvalSpec] = {}


def register(spec: EvalSpec) -> None:
    REGISTRY[spec.eval_id] = spec


def evals_for_trigger(trigger: str) -> list[EvalSpec]:
    return [s for s in REGISTRY.values() if trigger in s.triggers]


# ---- runtime config (set at engine boot from settings; defaults keep it off) ----
_enabled: bool = False
_blocking_overrides: set[str] = set()  # eval_ids forced blocking regardless of spec default


def set_evals_enabled(enabled: bool) -> None:
    global _enabled
    _enabled = bool(enabled)


def evals_enabled() -> bool:
    return _enabled


def set_blocking_overrides(eval_ids: list[str] | set[str]) -> None:
    global _blocking_overrides
    _blocking_overrides = set(eval_ids or [])


def is_blocking(spec: EvalSpec) -> bool:
    return spec.blocking or spec.eval_id in _blocking_overrides


def reset_eval_config() -> None:
    """Test helper — restore the off/measure-only defaults."""
    global _enabled, _blocking_overrides
    _enabled = False
    _blocking_overrides = set()


__all__ = [
    "REGISTRY",
    "EvalContext",
    "EvalResult",
    "EvalSpec",
    "evals_enabled",
    "evals_for_trigger",
    "is_blocking",
    "register",
    "reset_eval_config",
    "set_blocking_overrides",
    "set_evals_enabled",
]
