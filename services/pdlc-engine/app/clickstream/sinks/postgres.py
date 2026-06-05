"""Self-host sink — batched inserts into the `events` table.

Writes each EventEnvelope (including the Phase G traceability columns) via a
sync SQLAlchemy engine. Tolerant of write failures so the emitter drain never
crashes if Postgres is briefly unavailable. Verified via docker-compose.
"""

from __future__ import annotations

import logging

from event_schema import EventEnvelope

log = logging.getLogger("pdlc.clickstream.postgres")


class PostgresSink:
    def __init__(self, db_url: str):
        self._db_url = db_url
        self._engine = None

    def _ensure_engine(self):
        if self._engine is None:
            from ..config import settings
            from ..db.session import get_sync_engine

            self._engine = get_sync_engine(settings)
        return self._engine

    def write(self, batch: list[EventEnvelope]) -> None:
        if not batch:
            return
        try:
            from sqlalchemy import insert

            from ..db.models import Event

            rows = [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "schema_version": e.schema_version,
                    "ts": e.ts,
                    "org_id": e.org_id,
                    "squad_id": e.squad_id,
                    "initiative_id": e.initiative_id,
                    "application_id": e.application_id,
                    "project_id": e.project_id,
                    "repository": e.repository,
                    "domains": list(e.domains or []),
                    "roadmap_id": e.roadmap_id,
                    "prd_id": e.prd_id,
                    "user_story_id": e.user_story_id,
                    "plan_step": e.plan_step,
                    "session_id": e.session_id,
                    "correlation_id": e.correlation_id,
                    "causation_id": e.causation_id,
                    "actor": e.actor,
                    "payload": e.payload,
                }
                for e in batch
            ]
            with self._ensure_engine().begin() as conn:
                conn.execute(insert(Event), rows)
        except Exception as exc:  # never crash the drain loop
            log.warning("events insert failed (%d rows): %s", len(batch), exc)
