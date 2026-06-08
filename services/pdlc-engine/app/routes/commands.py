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

import re
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.local import Identity, get_principal, resolve_org
from ..runtime import get_dispatcher

router = APIRouter(prefix="/commands", tags=["commands"])

Command = Literal[
    "init", "brainstorm", "build", "ship",
    "decide", "whatif", "doctor", "rollback",
    "hotfix", "night-shift", "pause", "resume",
    "abandon", "release", "override", "compact",
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
    "abandon", "release", "override", "pause", "resume", "compact",
}


class InvokeCommandRequest(BaseModel):
    command: Command
    org_id: UUID | None = None  # ignored when auth is on (org comes from the token)
    project_id: UUID
    args: list[str] = []
    feature: str | None = None
    interaction_mode: Literal["sketch", "socratic"] = "sketch"
    # Client-supplied conversation/session id, so chat attachments uploaded before
    # the turn land under this same conversation's folder. Sanitized; else generated.
    session_id: str | None = None
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
    # Use the client's conversation id (so pre-uploaded attachments match this
    # conversation's folder), sanitized to keep thread_id's "org:project:session" shape.
    session_id = re.sub(r"[^A-Za-z0-9_-]", "", req.session_id)[:64] if req.session_id else ""
    session_id = session_id or str(uuid4())
    thread_id = f"{org_id}:{req.project_id}:{session_id}"
    state = _initial_state(req, thread_id, session_id, org_id)

    pending = get_dispatcher().start(thread_id, state)
    _record_turn(org_id, thread_id, str(req.project_id),
                 user=f"/{req.command}" + (f" {req.feature}" if req.feature else ""),
                 pending=pending)
    return InvokeCommandResponse(
        thread_id=thread_id,
        started=True,
        pending=pending.as_dict() if pending else None,
    )


def _record_turn(org_id, thread_id, project_id, *, user: str, pending) -> None:
    """Append the user turn + the agent's response to the durable transcript.
    Best-effort: never break the request on a transcript failure."""
    try:
        from ..persistence.transcript import get_transcript_store, summarize_pending

        store = get_transcript_store()
        store.append(org_id=org_id, thread_id=thread_id, project_id=project_id, role="user", text=user)
        store.append(org_id=org_id, thread_id=thread_id, project_id=project_id,
                     role="agent", text=summarize_pending(pending))
    except Exception:  # pragma: no cover - never fail a turn on transcript
        pass


class ContinueRequest(BaseModel):
    thread_id: str
    org_id: UUID | None = None
    prompt: str


class ContinueResponse(BaseModel):
    thread_id: str
    response: str


_CONTINUE_SYSTEM = (
    "You are Atlas, continuing an ongoing pdlcflow conversation. Use the prior "
    "conversation below as context and respond helpfully and concisely to the new message."
)


def _render_history(entries: list[dict]) -> str:
    who = {"user": "User", "agent": "Assistant"}
    return "\n\n".join(f"{who.get(e['role'], 'System')}: {e['text']}" for e in entries)


@router.post("/continue", response_model=ContinueResponse)
def continue_thread(
    req: ContinueRequest,
    principal: Identity | None = Depends(get_principal),
) -> ContinueResponse:
    """Continue an existing conversation: the full prior transcript is sent to the
    LLM as context, followed by the new prompt. Appends both turns to the thread.
    """
    parts = req.thread_id.split(":")
    thread_org = parts[0] if parts else ""
    project_id = parts[1] if len(parts) >= 2 else None
    org_id = resolve_org(principal, str(req.org_id) if req.org_id else thread_org, "/v1/commands/continue")
    if org_id != thread_org:
        raise HTTPException(status_code=403, detail="thread does not belong to this org")

    from pdlc_graph.llm_port import complete, reset_thread_context, set_thread_context
    from pdlc_graph.ports import reset_current_org, set_current_org

    from ..persistence.transcript import get_transcript_store

    store = get_transcript_store()
    history = _render_history(store.list_thread(org_id=org_id, thread_id=req.thread_id))
    full = (f"Prior conversation:\n\n{history}\n\n---\n\nNew message:\n{req.prompt}"
            if history else req.prompt)

    tok_t = set_thread_context(req.thread_id)
    tok_o = set_current_org(org_id)
    try:
        response = complete("atlas", full, system=_CONTINUE_SYSTEM)
    finally:
        reset_thread_context(tok_t)
        reset_current_org(tok_o)

    try:
        store.append(org_id=org_id, thread_id=req.thread_id, project_id=project_id, role="user", text=req.prompt)
        store.append(org_id=org_id, thread_id=req.thread_id, project_id=project_id, role="agent", text=response)
    except Exception:  # pragma: no cover
        pass
    return ContinueResponse(thread_id=req.thread_id, response=response)
