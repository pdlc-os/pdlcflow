"""Execution context — the seam that tells engine backends WHICH repo/branch a
turn is operating on (execution arc).

The real test runner / VCS / deploy / security backends live engine-side and run
against a checked-out workspace. They need to resolve the project's repository
and the feature branch — which only the turn's state knows. The engine runner
binds this contextvar per turn (from the turn's PDLCState / thread id); the
backends read it. When nothing is bound (or execution is disabled), backends
fall back to their simulated defaults.

Dep-free (a plain contextvar), exactly like `set_current_org` — the graph
package gains no engine dependency.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    project_id: str
    feature: str | None = None
    branch: str | None = None  # the feature branch; None → derive from feature


_ctx: ContextVar[ExecutionContext | None] = ContextVar("pdlc_execution_ctx", default=None)


def set_execution_context(ctx: ExecutionContext | None):
    """Bind the turn's execution context; returns a token for reset."""
    return _ctx.set(ctx)


def reset_execution_context(token) -> None:
    _ctx.reset(token)


def current_execution_context() -> ExecutionContext | None:
    return _ctx.get()
