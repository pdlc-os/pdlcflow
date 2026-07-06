"""Observability — OpenTelemetry traces + metrics for the Nexus dashboard.

`wire_tracing(settings)` (called from the FastAPI lifespan) stands up the OTel
SDK, injects an OTel-backed tracer into pdlc-graph's dep-free tracing port, and
exposes span + metric helpers used by the runtime. Everything degrades to a
no-op when `PDLC_OTEL_ENABLED` is false, so dev/test/CI stay hermetic.
"""

from .tracing import (
    llm_span,
    record_breaker,
    record_fallback,
    record_gate,
    record_llm,
    record_rate_limited,
    record_turn,
    turn_span,
    wire_tracing,
)

__all__ = [
    "llm_span",
    "record_breaker",
    "record_fallback",
    "record_gate",
    "record_llm",
    "record_rate_limited",
    "record_turn",
    "turn_span",
    "wire_tracing",
]
