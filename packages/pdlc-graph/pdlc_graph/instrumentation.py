"""@instrumented_node — wraps every graph node with event emission.

The emitter is injected via a module-level setter so the graph package stays
free of the engine's runtime dependencies (FastAPI, asyncpg). At engine boot,
`services/pdlc-engine/app/main.py` calls `set_emitter(my_emitter)` and the
decorator picks it up from there.
"""

from __future__ import annotations

import functools
import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from . import tracing

try:  # langgraph control-flow signals (interrupt(), Command bubbling) — NOT errors
    from langgraph.errors import GraphBubbleUp as _ControlFlow
except Exception:  # pragma: no cover - older/newer langgraph
    class _ControlFlow(Exception):  # type: ignore[no-redef]
        ...


class _EmitterProto(Protocol):
    def emit(self, event_type: str, state: dict, payload: dict, correlation_id: str) -> None: ...


class _NullEmitter:
    def emit(self, *_args: Any, **_kw: Any) -> None:
        return None


_emitter: _EmitterProto = _NullEmitter()


def set_emitter(emitter: _EmitterProto) -> None:
    global _emitter
    _emitter = emitter


def emit_event(event_type: str, state: dict, payload: dict, correlation_id: str | None = None) -> None:
    """Emit a typed event with an explicit payload from inside a node.

    The `@instrumented_node` decorator only emits node enter/exit; use this when
    a node needs to publish a value (e.g. a Sentinel verdict) the decorator
    can't see in the input state.
    """
    corr = correlation_id or state.get("correlation_id") or str(uuid.uuid4())
    _emitter.emit(event_type, state, payload, corr)


def evaluate(
    trigger: str,
    state: dict,
    output: str,
    *,
    target: str,
    sources: dict[str, str] | None = None,
    extra: dict | None = None,
) -> list:
    """Run the evals registered for `trigger` over one agent output, emitting
    `eval.scored` (always) and `eval.blocked` (for failed blocking evals).

    Strict no-op — returns [] — unless evals are enabled at boot
    (`PDLC_RUN_EVALS`). Never raises into the calling node. Returns the list of
    EvalResult so a node can optionally enforce (see evals.blocking_failures).
    """
    try:
        from .evals import EvalContext, run_evals_for
    except Exception:  # pragma: no cover - evals package always present
        return []
    ctx = EvalContext(
        trigger=trigger, target=target, output=output or "",
        sources=sources or {}, state=state, extra=extra or {},
    )
    results = run_evals_for(ctx)
    for r in results:
        emit_event("eval.scored", state, r.to_payload())
        if r.blocking and not r.passed:
            emit_event(
                "eval.blocked", state,
                {"eval_id": r.eval_id, "gate": trigger, "dimension": r.dimension,
                 "score": round(float(r.score), 4), "threshold": r.threshold,
                 "reason": r.rationale[:300]},
            )
    return results


def _span_attrs(fn_name: str, event_type: str, state: dict) -> dict:
    """OTel attributes for a node span — tenancy + workflow position, so the
    trace tree can be sliced by org/project/thread/phase/agent in Grafana."""
    attrs = {
        "pdlc.node": fn_name,
        "pdlc.event_type": event_type,
        "pdlc.phase": state.get("phase"),
        "pdlc.org_id": state.get("org_id"),
        "pdlc.project_id": state.get("project_id"),
        "pdlc.thread_id": state.get("thread_id"),
        "pdlc.initiative_id": state.get("initiative_id"),
        "pdlc.squad_id": state.get("squad_id"),
        "pdlc.agent_persona": state.get("agent_persona"),
    }
    return {k: v for k, v in attrs.items() if v is not None}


def instrumented_node(event_type: str) -> Callable:
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapped(state: dict) -> dict:
            corr = state.get("correlation_id") or str(uuid.uuid4())
            t0 = time.time()
            _emitter.emit(event_type, state, {"node": fn.__name__, "phase": "enter"}, corr)
            # One OTel span per node execution — this is the "across multiple
            # agents" view: nested under the engine's per-turn root span, the
            # span tree shows which persona/node ran when. No-op unless the
            # engine injected a tracer (see pdlc_graph.tracing).
            with tracing.span(
                f"pdlc.node.{fn.__name__}",
                kind="internal",
                attributes=_span_attrs(fn.__name__, event_type, state),
            ) as _span:
                try:
                    out = fn(state)
                except _ControlFlow:
                    # interrupt() / Command bubbling pauses the graph — control
                    # flow, not a failure. Re-raise without a spurious error event.
                    raise
                except Exception as exc:
                    _span.record_exception(exc)
                    _emitter.emit(
                        "error", state,
                        {"exc_type": type(exc).__name__, "where": fn.__name__},
                        corr,
                    )
                    raise
            _emitter.emit(
                event_type, state,
                {"node": fn.__name__, "phase": "exit",
                 "duration_ms": int((time.time() - t0) * 1000)},
                corr,
            )
            return out
        return wrapped
    return deco
