"""Approval-gate REST — list open interactions + resolve (resume the graph).

When the graph hits `interrupt()` the GraphRunner records a pending interaction
(an approval gate or a Socratic/Bloom's question round) in the GateStore and
pushes it over WebSocket. Studio POSTs back here to resolve it; the runner
resumes the thread with `Command(resume=...)` and reconciles the next pause.

Both interrupt kinds resume through here (plan §1.3):
- approval        → resume value `{"approved": bool, "comment": ..., "edit": ...}`
- user_input_*    → resume value `{"answers": [...]}`
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..runtime import get_gate_store, get_runner

router = APIRouter(prefix="/approval-gates", tags=["approval-gates"])


class Gate(BaseModel):
    id: UUID
    thread_id: str
    org_id: str
    project_id: str
    kind: str
    gate_kind: str | None
    payload: dict
    status: str


class ResolveRequest(BaseModel):
    # Approval gates use approved/comment/edit; question rounds use answers.
    approved: bool | None = None
    comment: str | None = None
    edit: dict | None = None
    answers: list[str] | None = None


class ResolveResponse(BaseModel):
    ok: bool
    thread_id: str
    pending: dict | None = None  # the NEXT interaction, or None if the thread advanced to completion


def _to_gate(rec) -> Gate:
    return Gate(
        id=rec.id,
        thread_id=rec.thread_id,
        org_id=rec.org_id,
        project_id=rec.project_id,
        kind=rec.kind,
        gate_kind=rec.gate_kind,
        payload=rec.payload,
        status=rec.status,
    )


@router.get("", response_model=list[Gate])
def list_open_gates(org_id: str | None = None, project_id: str | None = None) -> list[Gate]:
    recs = get_gate_store().list_open(org_id=org_id, project_id=project_id)
    return [_to_gate(r) for r in recs]


def _resume_value(rec, req: ResolveRequest):
    """Shape the resume payload to the interrupt kind."""
    if rec.kind == "approval":
        return {"approved": bool(req.approved), "comment": req.comment, "edit": req.edit}
    return {"answers": req.answers or []}


@router.post("/{gate_id}/resolve", response_model=ResolveResponse)
def resolve(gate_id: UUID, req: ResolveRequest) -> ResolveResponse:
    store = get_gate_store()
    rec = store.get(gate_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="gate not found")
    if rec.status != "open":
        raise HTTPException(status_code=409, detail=f"gate already {rec.status}")

    store.resolve(gate_id, status="resolved")
    next_pending = get_runner().resume(rec.thread_id, _resume_value(rec, req))
    return ResolveResponse(
        ok=True,
        thread_id=rec.thread_id,
        pending=next_pending.as_dict() if next_pending else None,
    )
