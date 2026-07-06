"""Migration import endpoint — ingest an upstream pdlc project in one POST.

The migration CLI (``pdlc-migrate``) scans an upstream project, reconstructs a
synthetic event history, and POSTs the shared "import payload" here. This route
turns that payload into durable engine state:

* ``events[]`` -> one :class:`event_schema.EventEnvelope` per event, fed to the
  analytics store. Each event gets a DETERMINISTIC ``event_id`` (uuid5) so a
  re-run of the same import ingests nothing new (the store dedups on event_id),
  and is stamped with the resolved ``initiative_id`` / ``application_id`` so
  migrated history shows up in those rollup dimensions (T3-3).
* ``memory_files[]`` -> persisted via the artifact port at
  ``migrated/{project_id}/{kind}.md``.
* ``tasks[]`` -> the durable task store (``bd-NN``/external_id preserved).
* ``decisions[]`` -> the Decision Registry artifact (DECISIONS.md).
* ``deployments[]`` -> the deployment record artifact (DEPLOYMENTS.md).

Everything is idempotent: events dedup on event_id; tasks skip on a duplicate
external_id; decisions/deployments render one deterministic artifact; entity
resolution upserts by name. The response reports ``received`` vs ``persisted``
per kind so partial support can never masquerade as success again (T1-5).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from event_schema import EventEnvelope
from fastapi import APIRouter, Depends
from pdlc_graph.ports import get_task_store, put_artifact, reset_current_org, set_current_org
from pdlc_graph.render import render_decisions, render_deployments
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..analytics import get_analytics_store
from ..auth.local import Identity, get_principal, resolve_org
from ..config import settings

log = logging.getLogger("pdlc.migrate")
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


def _db_available() -> bool:
    """Entity resolution needs the initiatives/applications tables — only when a
    Postgres backend is configured (hermetic/in-memory runs skip it)."""
    return getattr(settings, "task_store", "memory") == "postgres" or getattr(
        settings, "analytics_backend", "memory"
    ) == "postgres"


def _resolve_entities(org_id: str, taxonomy: Taxonomy) -> dict[str, str | None]:
    """Upsert-by-name the initiative + application for this org, returning their
    UUIDs (or None). DB-gated + fail-soft — a resolution failure must never fail
    the import (events still ingest, just without those dimensions)."""
    resolved: dict[str, str | None] = {"initiative_id": None, "application_id": None}
    if not _db_available():
        return resolved
    try:
        from ..db.rls import set_org_context
        from ..db.session import get_sync_engine

        engine = get_sync_engine(settings)
        with engine.begin() as conn:
            set_org_context(conn, org_id)
            init_id = None
            if taxonomy.initiative:
                init_id = _upsert_named(
                    conn, org_id, "initiatives", taxonomy.initiative,
                    extra_cols={"status": "active"})
                resolved["initiative_id"] = str(init_id)
            if taxonomy.application:
                app_id = _upsert_named(
                    conn, org_id, "applications", taxonomy.application,
                    extra_cols={"kind": "service"},
                    extra_vals={"initiative_id": init_id})
                resolved["application_id"] = str(app_id)
    except Exception as exc:  # never fail the import on resolution
        log.warning("entity resolution skipped (%s); events keep domains only",
                    type(exc).__name__)
    return resolved


def _upsert_named(conn, org_id: str, table: str, name: str, *,
                  extra_cols: dict[str, str], extra_vals: dict | None = None) -> uuid.UUID:
    """Find (or create) a row by (org_id, name) — these tables have no unique
    constraint on name, so it's select-then-insert under the RLS transaction."""
    existing = conn.execute(
        text(f"select id from {table} where org_id = :o and name = :n limit 1"),
        {"o": org_id, "n": name},
    ).scalar()
    if existing is not None:
        return existing
    new_id = uuid.uuid4()
    cols = ["id", "org_id", "name", *extra_cols.keys()]
    vals = {"id": str(new_id), "org_id": org_id, "name": name, **extra_cols}
    for k, v in (extra_vals or {}).items():
        if v is not None:
            cols.append(k)
            vals[k] = str(v)
    placeholders = ", ".join(f":{c}" for c in cols)
    conn.execute(
        text(f"insert into {table} ({', '.join(cols)}) values ({placeholders})"), vals)
    return new_id


def _persist_tasks(org_id: str, project_id: str, tasks: list[Task]) -> int:
    """Write tasks to the durable store, preserving external_id (bd-NN). Skips
    duplicates so re-import doesn't raise. Returns the count written."""
    store = get_task_store()
    persisted = 0
    for t in tasks:
        try:
            store.create(
                org_id=org_id, project_id=project_id, title=t.title,
                body="", labels=list(t.labels), external_id=t.external_id)
            persisted += 1
        except Exception as exc:  # duplicate external_id on re-import, etc.
            log.debug("task %s not written (%s)", t.external_id, type(exc).__name__)
    return persisted


@router.post("/import")
def import_project(
    payload: ImportPayload,
    principal: Identity | None = Depends(get_principal),
) -> dict:
    """Ingest an upstream project's events, memory files, tasks, decisions, and
    deployments; resolve taxonomy names to entity ids. Idempotent."""

    # auth on => org comes from the token (can't import into another org); admin-only.
    org_id = resolve_org(principal, payload.org_id, "/v1/migrate/import", admin=True)
    store = get_analytics_store()

    # Resolve initiative/application names to UUIDs so migrated events populate
    # those rollup dimensions (not just `domains`).
    entities = _resolve_entities(org_id, payload.taxonomy)
    init_uuid = uuid.UUID(entities["initiative_id"]) if entities["initiative_id"] else None
    app_uuid = uuid.UUID(entities["application_id"]) if entities["application_id"] else None

    envelopes: list[EventEnvelope] = []
    for ev in payload.events:
        envelopes.append(
            EventEnvelope(
                event_id=_deterministic_event_id(ev),
                event_type=ev.event_type,
                ts=ev.ts,
                org_id=uuid.UUID(org_id),
                project_id=uuid.UUID(payload.project_id),
                initiative_id=init_uuid,
                application_id=app_uuid,
                domains=list(payload.taxonomy.domains),
                roadmap_id=ev.roadmap_id,
                user_story_id=ev.user_story_id,
                payload=ev.payload,
            )
        )

    before = store.totals(org_id=org_id)["events"]
    store.ingest(envelopes)
    ingested = store.totals(org_id=org_id)["events"] - before

    # Bind the (authoritative) tenant so imported artifacts + tasks land under
    # this org's prefix / RLS scope — same isolation as graph-driven writes.
    org_tok = set_current_org(org_id)
    try:
        for mf in payload.memory_files:
            put_artifact(
                payload.project_id,
                f"migrated/{payload.project_id}/{mf.kind}.md",
                mf.body,
            )
        tasks_persisted = _persist_tasks(org_id, payload.project_id, payload.tasks)

        decisions_persisted = 0
        if payload.decisions:
            md = render_decisions([d.model_dump() for d in payload.decisions])
            put_artifact(payload.project_id, "docs/pdlc/memory/DECISIONS.md", md)
            decisions_persisted = len(payload.decisions)

        deployments_persisted = 0
        if payload.deployments:
            md = _render_deployments_doc(payload)
            put_artifact(payload.project_id, "docs/pdlc/memory/DEPLOYMENTS.md", md)
            deployments_persisted = len(payload.deployments)
    finally:
        reset_current_org(org_tok)

    return {
        "events": ingested,  # int (backfill CLI reads this); == 0 on re-import
        "memory_files": len(payload.memory_files),
        "tasks": tasks_persisted,
        "decisions": decisions_persisted,
        "deployments": deployments_persisted,
        "received": {
            "events": len(payload.events),
            "memory_files": len(payload.memory_files),
            "tasks": len(payload.tasks),
            "decisions": len(payload.decisions),
            "deployments": len(payload.deployments),
        },
        "entities": entities,
    }


def _render_deployments_doc(payload: ImportPayload) -> str:
    """Combine the imported deployment history into one DEPLOYMENTS.md. Uses the
    canonical single-deploy renderer for the newest, then appends the rest as
    history rows so the full record survives migration."""
    feature = payload.project_id
    deps = payload.deployments
    newest = deps[-1]
    doc = render_deployments(
        feature=feature, env=newest.env, tier=newest.tier, version=newest.version,
        url="(migrated — url not recorded)", sha="(migrated)", date=newest.date)
    if len(deps) > 1:
        extra = ["", "#### Migrated Deployment History", "",
                 "| Date | Version | Env | Tier |", "|------|---------|-----|------|"]
        for d in deps[:-1]:
            extra.append(f"| {d.date} | {d.version} | {d.env} | {d.tier} |")
        doc += "\n" + "\n".join(extra) + "\n"
    return doc
