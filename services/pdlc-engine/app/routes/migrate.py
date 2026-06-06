"""Migration import endpoint — ingest an upstream pdlc project in one POST.

The migration CLI (``pdlc-migrate``) scans an upstream project, reconstructs a
synthetic event history, and POSTs the shared "import payload" here. This route
turns that payload into durable engine state:

* ``events[]`` -> one :class:`event_schema.EventEnvelope` per event, fed to the
  analytics store. Each event gets a DETERMINISTIC ``event_id`` (uuid5) so a
  re-run of the same import ingests nothing new (the store dedups on event_id).
* ``memory_files[]`` -> persisted via the artifact port at
  ``migrated/{project_id}/{kind}.md``.

Tasks / decisions / deployments are echoed back in the response counts; their
durable rows land once the Postgres entity tables exist (Phase B).
"""

from __future__ import annotations

import uuid
from typing import Any

from event_schema import EventEnvelope
from fastapi import APIRouter, Depends
from pdlc_graph.ports import put_artifact
from pydantic import BaseModel, Field

from ..analytics import get_analytics_store
from ..auth.local import Identity, get_principal, resolve_org

router = APIRouter(prefix="/migrate", tags=["migrate"])


class Taxonomy(BaseModel):
    initiative: str | None = None
    application: str | None = None
    domains: list[str] = Field(default_factory=list)


class MemoryFile(BaseModel):
    kind: str
    path: str
    body: str


class Task(BaseModel):
    external_id: str
    title: str
    labels: list[str] = Field(default_factory=list)
    status: str


class Decision(BaseModel):
    id: str
    title: str
    date: str
    rationale: str


class Deployment(BaseModel):
    env: str
    tier: str
    version: str
    date: str


class ImportEvent(BaseModel):
    """One synthetic (or live) event in the import payload.

    ``event_id`` is optional: when present it seeds the deterministic uuid5 so
    re-imports collide and dedup; when absent the id is derived from
    ``event_type`` + ``ts``.
    """

    model_config = {"extra": "allow"}

    event_id: str | None = None
    event_type: str
    ts: str
    roadmap_id: str | None = None
    user_story_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ImportPayload(BaseModel):
    org_id: str
    project_id: str
    taxonomy: Taxonomy = Field(default_factory=Taxonomy)
    memory_files: list[MemoryFile] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    deployments: list[Deployment] = Field(default_factory=list)
    events: list[ImportEvent] = Field(default_factory=list)


def _deterministic_event_id(ev: ImportEvent) -> uuid.UUID:
    """uuid5 from the event's own id when present, else event_type+ts.

    Deterministic ids make the import idempotent: the analytics store dedups on
    ``event_id``, so a second identical POST adds zero events.
    """

    key = ev.event_id or f"{ev.event_type}|{ev.ts}"
    return uuid.uuid5(uuid.NAMESPACE_URL, key)


@router.post("/import")
def import_project(
    payload: ImportPayload,
    principal: Identity | None = Depends(get_principal),
) -> dict[str, int]:
    """Ingest an upstream project's events + memory files; echo entity counts."""

    # auth on => org comes from the token (can't import into another org); admin-only.
    org_id = resolve_org(principal, payload.org_id, "/v1/migrate/import", admin=True)
    store = get_analytics_store()

    envelopes: list[EventEnvelope] = []
    for ev in payload.events:
        envelopes.append(
            EventEnvelope(
                event_id=_deterministic_event_id(ev),
                event_type=ev.event_type,
                ts=ev.ts,
                org_id=uuid.UUID(org_id),
                project_id=uuid.UUID(payload.project_id),
                domains=list(payload.taxonomy.domains),
                roadmap_id=ev.roadmap_id,
                user_story_id=ev.user_story_id,
                payload=ev.payload,
            )
        )

    before = store.totals(org_id=org_id)["events"]
    store.ingest(envelopes)
    after = store.totals(org_id=org_id)["events"]

    for mf in payload.memory_files:
        put_artifact(
            payload.project_id,
            f"migrated/{payload.project_id}/{mf.kind}.md",
            mf.body,
        )

    return {
        "events": after - before,
        "memory_files": len(payload.memory_files),
        "tasks": len(payload.tasks),
        "decisions": len(payload.decisions),
        "deployments": len(payload.deployments),
    }
