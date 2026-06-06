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

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth.local import Identity, get_principal, resolve_org
from ..runtime import get_dispatcher

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

# Utility commands route to the utility subgraph via the `utility_command` flag,
# independent of the resting phase.
_UTILITY_COMMANDS: set[str] = {
    "decide", "whatif", "doctor", "rollback", "hotfix",
    "abandon", "release", "override", "pause", "resume",
}


class InvokeCommandRequest(BaseModel):
    command: Command
    org_id: UUID | None = None  # ignored when auth is on (org comes from the token)
    project_id: UUID
    args: list[str] = []
    feature: str | None = None
    interaction_mode: Literal["sketch", "socratic"] = "sketch"
    # Optional seed for the initial graph state — lets a client start a phase
    # mid-lifecycle (e.g. /build with a known task list). Tenancy + phase keys
    # are always re-asserted from the command and cannot be overridden.
    seed_state: dict | None = None


class InvokeCommandResponse(BaseModel):
    thread_id: str
    started: bool
    pending: dict | None = None  # the opened gate / question, if the graph paused


def _initial_state(req: InvokeCommandRequest, thread_id: str, session_id: str, org_id: str) -> dict:
    feature = req.feature or (req.args[0] if req.args else None)
    state: dict = dict(req.seed_state or {})
    # Authoritative keys win over anything in seed_state.
    state.update(
        {
            "org_id": org_id,
            "project_id": str(req.project_id),
            "session_id": session_id,
            "thread_id": thread_id,
            "phase": _PHASE_FOR_COMMAND.get(req.command, "Initialization"),
            "night_shift_active": req.command == "night-shift",
            "interaction_mode": req.interaction_mode,
        }
    )
    state.setdefault("feature", feature)
    state.setdefault("brainstorm_log", [])
    if req.command in _UTILITY_COMMANDS:
        state["utility_command"] = req.command
    return state


@router.post("", response_model=InvokeCommandResponse)
def invoke(
    req: InvokeCommandRequest,
    principal: Identity | None = Depends(get_principal),
) -> InvokeCommandResponse:
    org_id = resolve_org(principal, str(req.org_id) if req.org_id else None, "/v1/commands")
    session_id = str(uuid4())
    thread_id = f"{org_id}:{req.project_id}:{session_id}"
    state = _initial_state(req, thread_id, session_id, org_id)

    pending = get_dispatcher().start(thread_id, state)
    return InvokeCommandResponse(
        thread_id=thread_id,
        started=True,
        pending=pending.as_dict() if pending else None,
    )
