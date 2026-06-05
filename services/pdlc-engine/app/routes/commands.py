"""Slash-command REST surface — one POST that dispatches by name.

The 17 upstream commands (init, brainstorm, build, ship, decide, whatif,
doctor, rollback, hotfix, night-shift, pause, resume, abandon, release,
override, plus the pdlc root + setup alias) each enqueue a `start_graph`
Arq job and return a thread_id. Studio's command palette and the Atlas
Console wire to the same endpoint.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/commands", tags=["commands"])

Command = Literal[
    "init", "brainstorm", "build", "ship",
    "decide", "whatif", "doctor", "rollback",
    "hotfix", "night-shift", "pause", "resume",
    "abandon", "release", "override",
    "pdlc", "setup",
]


class InvokeCommandRequest(BaseModel):
    command: Command
    org_id: UUID
    project_id: UUID
    args: list[str] = []


class InvokeCommandResponse(BaseModel):
    thread_id: str
    enqueued: bool


@router.post("", response_model=InvokeCommandResponse)
def invoke(_req: InvokeCommandRequest) -> InvokeCommandResponse:
    # Phase A stub: no Arq enqueue yet — just returns a synthetic thread_id
    # so Studio's WS connect path is exercisable end-to-end.
    return InvokeCommandResponse(thread_id=str(uuid4()), enqueued=False)
