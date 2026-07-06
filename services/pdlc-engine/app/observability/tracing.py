"""OpenTelemetry wiring — traces + metrics, exported OTLP to the collector.

Signal model (see docs/wiki/19-observability.md):

  pdlc.turn                (root span, per graph turn — thread/org/project)
    └─ pdlc.node.<name>    (one per LangGraph node — the multi-agent tree)
         └─ pdlc.llm       (one per complete() call — GenAI semconv: model,
                            provider, token usage, cost)

Metrics (OTLP → collector → Prometheus):
  pdlc.turns                counter   {outcome}
  pdlc.turn.duration_ms     histogram
  pdlc.llm.calls            counter   {persona,provider,model,tier,status}
  pdlc.llm.tokens           counter   {persona,provider,model,direction}
  pdlc.llm.cost_usd         counter   {persona,provider,model}
  pdlc.llm.duration_ms      histogram {persona,provider,model}
  pdlc.gates                counter   {kind,action}

A pdlc *thread* is not a trace: it lives across many turns and human pauses, so
we open one trace per turn and correlate turns by the `pdlc.thread_id`
attribute. The long-horizon journey view is reconstructed by querying (the
Postgres clickstream / transcript), not by holding a span open across a pause.

All public helpers are safe no-ops until `wire_tracing()` succeeds.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator, Mapping
from typing import Any

log = logging.getLogger("pdlc.observability")

# Populated by wire_tracing(); None => OTel disabled, every helper is a no-op.
_TRACER: Any = None
_ENABLED = False

# Metric instruments (set in _init_metrics).
_M: dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# Graph tracer port adapter
# --------------------------------------------------------------------------- #
class _OtelTracerAdapter:
    """Implements pdlc_graph.tracing._TracerPort over an OTel tracer, so node
    spans opened inside the graph nest under our per-turn root span."""

    def __init__(self, tracer: Any) -> None:
        self._tracer = tracer
        from opentelemetry.trace import SpanKind

        self._kinds = {
            "internal": SpanKind.INTERNAL,
            "client": SpanKind.CLIENT,
            "server": SpanKind.SERVER,
            "producer": SpanKind.PRODUCER,
            "consumer": SpanKind.CONSUMER,
        }

    def span(self, name: str, *, kind: str = "internal", attributes: Mapping[str, Any] | None = None):
        return self._tracer.start_as_current_span(
            name,
            kind=self._kinds.get(kind, self._kinds["internal"]),
            attributes=dict(attributes or {}),
        )


# --------------------------------------------------------------------------- #
# Public span helpers (engine-side; native OTel)
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def turn_span(thread_id: str, org_id: str, project_id: str) -> Iterator[Any]:
    """Root span for one graph turn. No-op unless OTel is wired."""
    if not _ENABLED or _TRACER is None:
        yield None
        return
    from opentelemetry.trace import SpanKind

    attrs = {
        "pdlc.thread_id": thread_id,
        "pdlc.org_id": org_id,
        "pdlc.project_id": project_id,
    }
    with _TRACER.start_as_current_span("pdlc.turn", kind=SpanKind.SERVER, attributes=attrs) as span:
        yield span


@contextlib.contextmanager
def llm_span(persona: str, tier: str | None) -> Iterator[Any]:
    """Span for a single LLM completion. GenAI semconv attributes (model,
    provider, token usage) are filled in by the caller via the yielded span once
    the model result is known. No-op unless OTel is wired."""
    if not _ENABLED or _TRACER is None:
        yield None
        return
    from opentelemetry.trace import SpanKind

    attrs = {
        "gen_ai.operation.name": "chat",
        "pdlc.persona": persona,
        "pdlc.tier": tier or "premium",
    }
    with _TRACER.start_as_current_span(f"pdlc.llm.{persona}", kind=SpanKind.CLIENT, attributes=attrs) as span:
        yield span


# --------------------------------------------------------------------------- #
# Metric recorders
# --------------------------------------------------------------------------- #
def record_turn(outcome: str, duration_ms: float) -> None:
    if not _ENABLED or not _M:
        return
    with contextlib.suppress(Exception):
        _M["turns"].add(1, {"outcome": outcome})
        _M["turn_duration"].record(duration_ms, {"outcome": outcome})


def record_llm(
    *,
    persona: str,
    provider: str,
    model: str,
    tier: str,
    tokens_in: int,
    tokens_out: int,
    usd: float,
    duration_ms: float,
    ok: bool,
) -> None:
    if not _ENABLED or not _M:
        return
    with contextlib.suppress(Exception):
        base = {"persona": persona, "provider": provider, "model": model}
        _M["llm_calls"].add(1, {**base, "tier": tier, "status": "ok" if ok else "error"})
        if tokens_in:
            _M["llm_tokens"].add(tokens_in, {**base, "direction": "in"})
        if tokens_out:
            _M["llm_tokens"].add(tokens_out, {**base, "direction": "out"})
        if usd:
            _M["llm_cost"].add(usd, base)
        _M["llm_duration"].record(duration_ms, base)


def record_gate(kind: str, action: str) -> None:
    """action = opened | resolved; kind = the gate/interaction kind."""
    if not _ENABLED or not _M:
        return
    with contextlib.suppress(Exception):
        _M["gates"].add(1, {"kind": kind or "unknown", "action": action})


# Resilience metrics (PRD-05). No org_id label — unbounded cardinality; the
# org lives in span attributes + clickstream events, per convention.
def record_fallback(from_provider: str, reason: str) -> None:
    if not _ENABLED or not _M:
        return
    with contextlib.suppress(Exception):
        _M["llm_fallbacks"].add(1, {"from_provider": from_provider, "reason": reason})


def record_breaker(provider_key: str, transition: str) -> None:
    """transition = open | reopen | close (provider_key may carry the gateway
    endpoint host, e.g. 'openai_compatible:openrouter.ai')."""
    if not _ENABLED or not _M:
        return
    with contextlib.suppress(Exception):
        _M["llm_breaker"].add(1, {"provider": provider_key, "transition": transition})


def record_rate_limited(provider: str, tier: str) -> None:
    if not _ENABLED or not _M:
        return
    with contextlib.suppress(Exception):
        _M["llm_rate_limited"].add(1, {"provider": provider, "tier": tier})


# --------------------------------------------------------------------------- #
# Boot wiring
# --------------------------------------------------------------------------- #
def _init_metrics(meter: Any) -> None:
    global _M
    _M = {
        "turns": meter.create_counter("pdlc.turns", description="Graph turns started, by outcome"),
        "turn_duration": meter.create_histogram(
            "pdlc.turn.duration_ms", unit="ms", description="Wall-clock duration of a graph turn"),
        "llm_calls": meter.create_counter("pdlc.llm.calls", description="LLM completions, by status"),
        "llm_tokens": meter.create_counter("pdlc.llm.tokens", description="LLM token usage (in/out)"),
        "llm_cost": meter.create_counter("pdlc.llm.cost_usd", description="Estimated LLM spend (USD)"),
        "llm_duration": meter.create_histogram(
            "pdlc.llm.duration_ms", unit="ms", description="LLM completion latency"),
        "gates": meter.create_counter("pdlc.gates", description="Approval gates / question rounds"),
        "llm_fallbacks": meter.create_counter(
            "pdlc.llm.fallbacks", description="Failover attempts to the next chain candidate"),
        "llm_breaker": meter.create_counter(
            "pdlc.llm.breaker_transitions", description="Circuit-breaker state transitions"),
        "llm_rate_limited": meter.create_counter(
            "pdlc.llm.rate_limited", description="Completions rejected by the per-org RPM limit"),
    }


def wire_tracing(settings) -> bool:
    """Stand up the OTel SDK and inject the graph tracer. Returns True if
    enabled. Guarded by `settings.otel_enabled`; any failure leaves the no-op
    tracer in place so the engine still boots."""
    global _TRACER, _ENABLED
    if not getattr(settings, "otel_enabled", False):
        return False
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = getattr(settings, "otel_endpoint", "http://otel-collector:4317")
        resource = Resource.create(
            {
                "service.name": getattr(settings, "otel_service_name", "pdlc-engine"),
                "service.namespace": "pdlcflow",
                "deployment.environment": getattr(settings, "environment", "dev"),
            }
        )

        # Traces → collector → Tempo.
        tp = TracerProvider(resource=resource)
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        if getattr(settings, "otel_console_export", False):
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

            tp.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(tp)

        # Metrics → collector → Prometheus.
        readers = [
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=endpoint, insecure=True),
                export_interval_millis=int(getattr(settings, "otel_metric_interval_s", 15)) * 1000,
            )
        ]
        mp = MeterProvider(resource=resource, metric_readers=readers)
        metrics.set_meter_provider(mp)

        _TRACER = trace.get_tracer("pdlc.engine")
        _init_metrics(metrics.get_meter("pdlc.engine"))

        # Inject the OTel-backed tracer into the graph's dep-free port so node
        # spans nest under our per-turn root span.
        from pdlc_graph.tracing import set_tracer

        set_tracer(_OtelTracerAdapter(_TRACER))

        _ENABLED = True
        log.info("OpenTelemetry enabled — exporting OTLP to %s", endpoint)
        return True
    except Exception as exc:  # never block boot on telemetry
        log.warning("OTel wiring failed (%s); telemetry disabled", exc)
        _ENABLED = False
        return False


def instrument_fastapi(app, settings) -> None:
    """Add server-side HTTP request spans. Best-effort; safe if the instrumentor
    package is missing or OTel is disabled."""
    if not _ENABLED or not getattr(settings, "otel_instrument_fastapi", True):
        return
    with contextlib.suppress(Exception):
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
        log.info("FastAPI request spans instrumented")
