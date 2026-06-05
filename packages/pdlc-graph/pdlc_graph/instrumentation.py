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


def instrumented_node(event_type: str) -> Callable:
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapped(state: dict) -> dict:
            corr = state.get("correlation_id") or str(uuid.uuid4())
            t0 = time.time()
            _emitter.emit(event_type, state, {"node": fn.__name__, "phase": "enter"}, corr)
            try:
                out = fn(state)
            except _ControlFlow:
                # interrupt() / Command bubbling pauses the graph — control flow,
                # not a failure. Re-raise without emitting a spurious error event.
                raise
            except Exception as exc:
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
