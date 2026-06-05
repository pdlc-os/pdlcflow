"""ClickstreamEmitter — bounded queue, fire-and-forget, never blocks.

The emitter is wired at app start (`wire_emitter(settings)` in lifespan) and
also pushed into pdlc-graph's instrumentation module so every decorated node
emits without taking a runtime dependency on the engine.
"""

from __future__ import annotations

import logging
import queue
import threading

from event_schema import EventEnvelope

from ..config import Settings
from .sinks.firehose import FirehoseSink
from .sinks.jsonl import JsonlFileSink
from .sinks.postgres import PostgresSink

log = logging.getLogger("pdlc.clickstream")

_emitter: ClickstreamEmitter | None = None


class _Sink:
    def write(self, batch: list[EventEnvelope]) -> None: ...


class ClickstreamEmitter:
    def __init__(self, sink: _Sink, analytics=None, max_queue: int = 10_000):
        self._q: queue.Queue[EventEnvelope] = queue.Queue(maxsize=max_queue)
        self._sink = sink
        self._analytics = analytics  # read-store fan-out for Atlas Console
        threading.Thread(target=self._drain, daemon=True).start()

    def emit_envelope(self, e: EventEnvelope) -> None:
        try:
            self._q.put_nowait(e)
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(e)
            except queue.Full:
                log.warning("clickstream queue full; dropping")

    # Convenience: callable signature compatible with pdlc-graph's instrumentation
    def emit(self, event_type: str, state: dict, payload: dict, correlation_id: str) -> None:
        try:
            envelope = EventEnvelope(
                event_type=event_type,
                org_id=state["org_id"],
                project_id=state["project_id"],
                squad_id=state.get("squad_id"),
                initiative_id=state.get("initiative_id"),
                application_id=state.get("application_id"),
                repository=state.get("repository"),
                domains=state.get("domains", []),
                roadmap_id=state.get("roadmap_id"),
                prd_id=state.get("prd_id"),
                user_story_id=state.get("user_story_id"),
                plan_step=state.get("plan_step"),
                session_id=state.get("session_id"),
                thread_id=state.get("thread_id"),
                actor=state.get("actor"),
                correlation_id=correlation_id,  # type: ignore[arg-type]
                payload=payload,
            )
            self.emit_envelope(envelope)
        except Exception as exc:  # never raise on instrumentation
            log.warning("emit failed: %s", exc)

    def _drain(self) -> None:
        while True:
            batch: list[EventEnvelope] = [self._q.get()]
            try:
                while len(batch) < 200:
                    batch.append(self._q.get_nowait())
            except queue.Empty:
                pass
            try:
                self._sink.write(batch)
            except Exception as exc:
                log.warning("sink write failed: %s", exc)
            if self._analytics is not None:
                try:
                    self._analytics.ingest(batch)
                except Exception as exc:
                    log.warning("analytics ingest failed: %s", exc)


def _build_sink(settings: Settings) -> _Sink:
    if settings.clickstream_sink == "firehose":
        return FirehoseSink(stream_name=settings.firehose_stream_name or "pdlcflow-events")
    if settings.clickstream_sink == "postgres":
        return PostgresSink(db_url=settings.db_url)
    return JsonlFileSink()


def wire_emitter(settings: Settings) -> ClickstreamEmitter:
    global _emitter
    from ..analytics import get_analytics_store

    _emitter = ClickstreamEmitter(_build_sink(settings), analytics=get_analytics_store())

    # Push into pdlc-graph's instrumentation hook so decorated nodes emit.
    try:
        from pdlc_graph.instrumentation import set_emitter
        set_emitter(_emitter)
    except Exception:  # pdlc-graph is an optional dep at boot
        pass
    return _emitter


def get_emitter() -> ClickstreamEmitter:
    if _emitter is None:
        raise RuntimeError("emitter not wired; call wire_emitter() in lifespan")
    return _emitter
