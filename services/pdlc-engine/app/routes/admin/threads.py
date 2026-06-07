"""Conversation history — list past threads for an org/project and open one
(verbatim transcript + any open interaction) so the Studio can replay/continue.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...persistence.transcript import get_transcript_store
from ...runtime.ports import get_gate_store
from ._guard import admin_org

router = APIRouter(prefix="/threads", tags=["admin", "threads"])


@router.get("")
def list_threads(
    org_id: str = Depends(admin_org("/admin/threads")),
    project_id: str | None = Query(None),
) -> dict:
    return {"threads": get_transcript_store().list_threads(org_id=org_id, project_id=project_id)}


@router.get("/{thread_id}")
def open_thread(
    thread_id: str,
    org_id: str = Depends(admin_org("/admin/threads")),
) -> dict:
    transcript = get_transcript_store().list_thread(org_id=org_id, thread_id=thread_id)
    # Surface any still-open interaction so the Studio can continue the thread.
    pending = None
    for rec in get_gate_store().list_open(org_id=org_id, project_id=None):
        if rec.thread_id == thread_id:
            pending = {"id": str(rec.id), "kind": rec.kind, "gate_kind": rec.gate_kind,
                       "payload": rec.payload}
            break
    return {"thread_id": thread_id, "transcript": transcript, "pending": pending}
