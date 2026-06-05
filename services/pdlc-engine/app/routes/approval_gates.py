"""Approval-gate REST — open list + resolve.

When the LangGraph hits `interrupt()`, the worker writes an approval_gates row
and the engine forwards the payload over WebSocket. Studio POSTs back here to
resume the graph with `Command(resume={...})`.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/approval-gates", tags=["approval-gates"])


class Gate(BaseModel):
    id: UUID
    project_id: UUID
    thread_id: str
    gate_kind: str
    payload: dict
    status: Literal["open", "approved", "rejected", "edited", "expired"]
    opened_at: str


class ResolveRequest(BaseModel):
    approved: bool
    comment: str | None = None
    edit: dict | None = None


class ResolveResponse(BaseModel):
    ok: bool
    resumed_thread_id: str


@router.get("", response_model=list[Gate])
def list_open_gates() -> list[Gate]:
    return []  # Phase A stub — DB query lands in Phase B


@router.post("/{gate_id}/resolve", response_model=ResolveResponse)
def resolve(gate_id: UUID, _req: ResolveRequest) -> ResolveResponse:
    # Real: graph.invoke(Command(resume=...), config={"configurable": {"thread_id": ...}})
    return ResolveResponse(ok=True, resumed_thread_id=str(gate_id))
