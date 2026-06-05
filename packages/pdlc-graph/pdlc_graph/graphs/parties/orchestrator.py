"""Party-meeting orchestrator — one pattern serves every party kind.

Pattern (plan §2.6): fan out to N personas in parallel via `Send`, collect
their pitches with an additive reducer, then a consensus node renders a MOM
artifact and produces a binding decision. Under `/night-shift` the consensus
node auto-picks and tags the MOM instead of pausing for ratification.

Inception uses three party kinds — `progressive-thinking` (Discover, always),
`threat-model` and `design-laws` (Design, on triage). The triage gate
(`triage_level`) decides skip / lite / full before a party is ever convened.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...ports import put_artifact
from ...render import render_mom


class PartyState(TypedDict, total=False):
    # inputs
    feature: str
    project_id: str
    party_kind: str  # topic slug: progressive-thinking | threat-model | design-laws
    party_topic: str  # the question put to the room
    party_context: str
    party_roster: list[str]  # persona names
    night_shift_active: bool
    # accumulated
    pitches: Annotated[list[dict], operator.add]
    # outputs
    mom_ref: str
    decision: str
    auto: bool


def triage_level(signals: list[bool]) -> str:
    """Skip / Lite / Full from a 3-signal checklist (upstream triage gate).

    0 yes -> skip · 1 yes -> lite (lead solo) · 2-3 yes -> full (party).
    """
    yes = sum(1 for s in signals if s)
    if yes == 0:
        return "skip"
    if yes == 1:
        return "lite"
    return "full"


@instrumented_node("party.opened")
def _fan_out(state: PartyState) -> dict:
    return {"pitches": []}


def _dispatch(state: PartyState) -> list[Send]:
    roster = state.get("party_roster") or []
    return [Send("pitch", {**state, "_persona": p}) for p in roster]


@instrumented_node("party.pitch_received")
def _pitch(state: dict) -> dict:
    persona = state["_persona"]
    topic = state.get("party_topic", "")
    context = state.get("party_context", "")
    prompt = f"Party: {state.get('party_kind')}\nTopic: {topic}\nContext: {context}"
    pitch = complete(persona, prompt)
    return {"pitches": [{"persona": persona, "pitch": pitch}]}


@instrumented_node("party.consensus_reached")
def _consensus(state: PartyState) -> dict:
    auto = bool(state.get("night_shift_active"))
    pitches = state.get("pitches", [])
    decision = (
        "auto-pick (night-shift): proceed with synthesized consensus"
        if auto
        else "consensus reached; recommendation forwarded to lead"
    )
    mom = render_mom(
        feature=state.get("feature", "unknown"),
        topic=state.get("party_kind", "party"),
        mode="agent-teams",
        participants=[p["persona"] for p in pitches],
        context=state.get("party_context", ""),
        pitches=pitches,
        decision=decision,
        next_steps=["lead records decision", "findings flow to the design package"],
    )
    uri = put_artifact(
        state.get("project_id", "unknown"),
        f"mom/{state.get('feature', 'feature')}_{state.get('party_kind', 'party')}.md",
        mom,
    )
    return {"mom_ref": uri, "decision": decision, "auto": auto}


def build_party_graph(kind: str) -> Any:
    """Compile a party subgraph for `kind` (the topic slug)."""
    g = StateGraph(PartyState)
    g.add_node("fan_out", _fan_out)
    g.add_node("pitch", _pitch)
    g.add_node("consensus", _consensus)
    g.add_edge(START, "fan_out")
    g.add_conditional_edges("fan_out", _dispatch, ["pitch"])
    g.add_edge("pitch", "consensus")
    g.add_edge("consensus", END)
    return g.compile()


def run_party(
    *,
    feature: str,
    project_id: str,
    kind: str,
    topic: str,
    roster: list[str],
    context: str = "",
    night_shift_active: bool = False,
) -> dict:
    """Convenience: run a party to completion and return its result dict.

    Sub-phase nodes call this directly (rather than nesting the compiled graph)
    so the party is a normal function call inside the Design node.
    """
    graph = build_party_graph(kind)
    out = graph.invoke(
        {
            "feature": feature,
            "project_id": project_id,
            "party_kind": kind,
            "party_topic": topic,
            "party_context": context,
            "party_roster": roster,
            "night_shift_active": night_shift_active,
            "pitches": [],
        }
    )
    return {
        "mom_ref": out.get("mom_ref"),
        "decision": out.get("decision"),
        "pitches": out.get("pitches", []),
        "auto": out.get("auto", False),
    }
