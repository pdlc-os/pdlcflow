"""Self-host sink — batched inserts into the `events` table."""

from __future__ import annotations

from event_schema import EventEnvelope


class PostgresSink:
    def __init__(self, db_url: str):
        self._db_url = db_url
        # Phase A: connection pool init lands in lifespan once Alembic head
        # exists; the drain loop tolerates write failures so the absence of
        # a pool doesn't crash the emitter.

    def write(self, batch: list[EventEnvelope]) -> None:
        # Real: asyncpg copy_records_to_table into `events`. Stub for now.
        return None
