"""Tracing port — the graph package's seam to OpenTelemetry.

Mirrors the injectable-port pattern used by `instrumentation.set_emitter` and
`llm_port.set_completion_backend`: the graph package stays free of the OTel SDK
(and the engine's runtime deps). Nodes call `span(...)` here; until the engine
injects a real tracer via `set_tracer(...)`, a `_NullTracer` answers and every
span is a no-op context manager — so the whole graph runs in CI with no
OpenTelemetry installed, no collector, and byte-identical behaviour.

At boot the engine's `app.observability.tracing.wire_tracing()` installs an
OTel-backed tracer whose `span()` delegates to `start_as_current_span`, so node
spans nest under the engine's per-turn root span (OTel context propagates
through contextvars across the graph↔engine call boundary in-process).

Span kinds are passed as plain strings ("internal", "client", "server") so the
port has no OTel type dependency; the engine adapter maps them to SpanKind.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Protocol


class _Span(Protocol):
    def set_attribute(self, key: str, value: Any) -> None: ...
    def record_exception(self, exc: BaseException) -> None: ...


class _TracerPort(Protocol):
    # Returns a context manager yielding a span handle.
    def span(self, name: str, *, kind: str, attributes: Mapping[str, Any]) -> Any: ...


class _NullSpan:
    """A span handle that records nothing (the default, no-SDK path)."""

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def record_exception(self, exc: BaseException) -> None:
        return None


class _NullTracer:
    @contextmanager
    def span(self, name: str, *, kind: str = "internal", attributes: Mapping[str, Any] | None = None) -> Iterator[_NullSpan]:
        yield _NullSpan()


_tracer: _TracerPort = _NullTracer()


def set_tracer(tracer: _TracerPort) -> None:
    """Engine boot calls this with an OpenTelemetry-backed implementation."""
    global _tracer
    _tracer = tracer


def reset_tracer() -> None:
    """Restore the no-op tracer (used by tests)."""
    global _tracer
    _tracer = _NullTracer()


@contextmanager
def span(
    name: str,
    *,
    kind: str = "internal",
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[Any]:
    """Open a span named `name`. A no-op unless the engine injected a tracer.

    Yields a span handle with `.set_attribute()` / `.record_exception()`. Never
    raises out of the tracing layer — telemetry must not break a graph turn.
    """
    try:
        cm = _tracer.span(name, kind=kind, attributes=attributes or {})
    except Exception:  # pragma: no cover - tracer construction must never break a turn
        yield _NullSpan()
        return
    with cm as handle:
        yield handle


def is_traced() -> bool:
    return not isinstance(_tracer, _NullTracer)
