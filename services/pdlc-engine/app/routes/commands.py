"""Slash-command REST surface — one POST that dispatches by name.

The upstream commands each start (or resume) a graph thread. This wires the
real path: build the initial PDLCState from the command, run the meta-graph to
its first pause via the GraphRunner, and return the thread id plus any pending
interaction (an approval gate or a question round) the graph opened.

In production the start is enqueued to Arq and a worker drives the turn (the
worker's `start_graph` calls the same GraphRunner); for the single-process
dev/self-host path the turn runs inline here so the WS connect path is
immediately exercisable.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from ..runtime import get_runner

router = APIRouter(prefix="/commands", tags=["commands"])

Command = Literal[
    "init", "brainstorm", "build", "ship",
    "decide", "whatif", "doctor", "rollback",
    "hotfix", "night-shift", "pause", "resume",
    "abandon", "release", "override",
    "pdlc", "setup",
]

# Command → the phase the meta-router dispatches on.
_PHASE_FOR_COMMAND: dict[str, str] = {
    "init": "Initialization",
    "setup": "Initialization",
    "brainstorm": "Inception",
    "build": "Construction",
    "ship": "Operation",
}


class InvokeCommandRequest(BaseModel):
    command: Command
    org_id: UUID
    project_id: UUID
    args: list[str] = []
    feature: str | None = None
    interaction_mode: Literal["sketch", "socratic"] = "sketch"


class InvokeCommandResponse(BaseModel):
    thread_id: str
    started: bool
    pending: dict | None = None  # the opened gate / question, if the graph paused


def _initial_state(req: InvokeCommandRequest, thread_id: str, session_id: str) -> dict:
    feature = req.feature or (req.args[0] if req.args else None)
    return {
        "org_id": str(req.org_id),
        "project_id": str(req.project_id),
        "session_id": session_id,
        "thread_id": thread_id,
        "phase": _PHASE_FOR_COMMAND.get(req.command, "Initialization"),
        "night_shift_active": req.command == "night-shift",
        "interaction_mode": req.interaction_mode,
        "feature": feature,
        "brainstorm_log": [],
    }


@router.post("", response_model=InvokeCommandResponse)
def invoke(req: InvokeCommandRequest) -> InvokeCommandResponse:
    session_id = str(uuid4())
    thread_id = f"{req.org_id}:{req.project_id}:{session_id}"
    state = _initial_state(req, thread_id, session_id)

    pending = get_runner().start(thread_id, state)
    return InvokeCommandResponse(
        thread_id=thread_id,
        started=True,
        pending=pending.as_dict() if pending else None,
    )
