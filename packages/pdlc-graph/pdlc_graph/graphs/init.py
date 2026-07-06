"""Initialization subgraph — genesis setup before Inception (T3-2).

Models the upstream init skill (skills/init/steps/*.md): a short interactive
flow that seeds a project's governing memory, then hands off to Inception.

    START -> gather -> author -> init_gate -> END
              (ask rounds)  (render 3 artifacts)  (init_approve)

- gather    — three `interaction.ask` rounds (product intent, constitution
              choices, seed roadmap). Under night-shift the drafts auto-accept.
- author    — `complete()` drafts the prose, deterministic renderers assemble
              CONSTITUTION.md / INTENT.md / ROADMAP.md, `put_artifact` persists
              them, refs stashed in state.
- init_gate — the `init_approve` gate (gate #1 of 9). On approval, phase is set
              to "Inception" so the meta-graph routes the next turn to
              brainstorm; on rejection the phase stays "Initialization".

Compiled with a checkpointer by the engine so the ask/gate interrupts resume.
"""

from __future__ import annotations

from datetime import date as _date

from langgraph.graph import END, START, StateGraph

from .. import gates, interaction
from ..instrumentation import instrumented_node
from ..llm_port import complete
from ..ports import put_artifact
from ..render import render_constitution, render_intent, render_roadmap
from ..state import PDLCState

GATE_KIND = "init_approve"

# One ask() per round (mirrors Discover's Socratic cadence).
INIT_ROUNDS: list[tuple[str, list[str]]] = [
    (
        "Product intent",
        [
            "In one sentence, what is this project's mission?",
            "Who are the target users, and in what context?",
            "What does success look like — which metric moves, and by how much?",
        ],
    ),
    (
        "Constitution",
        [
            "Any governing principles beyond the PDLC defaults (TDD, prod-deploy ban, merge-commits-only)?",
            "Default interaction mode for this project — sketch or socratic?",
        ],
    ),
    (
        "Seed roadmap",
        [
            "List the first few features to build (one per line).",
            "For each, a one-line rationale (optional).",
        ],
    ),
]


def _draft(persona: str, prompt: str) -> str:
    return complete(persona, prompt, system="PDLC initialization facilitator").strip()


@instrumented_node("phase.entered")
def gather(state: PDLCState) -> dict:
    """Ask the three genesis rounds; stash raw answers for the author node."""
    project = state.get("project_name") or state.get("feature") or "the project"
    collected: dict[str, list[str]] = {}
    for title, questions in INIT_ROUNDS:
        drafts = [_draft("atlas", f"For '{project}', draft an answer to: {q}") for q in questions]
        result = interaction.ask(
            state, questions, drafts=drafts, context=f"Initialization — {title}")
        collected[title] = list(result.get("answers") or [])
    return {"init_answers": collected, "sub_phase": "Initialization"}


@instrumented_node("subphase.entered")
def author(state: PDLCState) -> dict:
    """Render + persist the three genesis artifacts from the gathered answers."""
    project = state.get("project_name") or state.get("feature") or "the project"
    project_id = state.get("project_id") or "proj"
    today = _date.today().isoformat()
    answers = state.get("init_answers") or {}

    intent = answers.get("Product intent") or []
    mission = intent[0] if len(intent) > 0 else ""
    users = intent[1] if len(intent) > 1 else ""
    metric = intent[2] if len(intent) > 2 else ""

    consti = answers.get("Constitution") or []
    principles_raw = consti[0] if len(consti) > 0 else ""
    mode_raw = (consti[1] if len(consti) > 1 else "socratic").strip().lower()
    interaction_mode = "sketch" if "sketch" in mode_raw else "socratic"
    principles = [p.strip("-• ").strip() for p in principles_raw.splitlines() if p.strip()]

    roadmap = answers.get("Seed roadmap") or []
    titles = [t.strip("-• ").strip()
              for t in (roadmap[0] if len(roadmap) > 0 else "").splitlines() if t.strip()]
    rationales = [r.strip("-• ").strip()
                  for r in (roadmap[1] if len(roadmap) > 1 else "").splitlines() if r.strip()]
    items = [{"title": t, "rationale": rationales[i] if i < len(rationales) else ""}
             for i, t in enumerate(titles)]

    constitution_md = render_constitution(
        project=project, date=today, principles=principles,
        interaction_mode=interaction_mode)
    intent_md = render_intent(
        project=project, date=today, mission=mission, target_users=users,
        success_metrics=[metric] if metric else None)
    roadmap_md = render_roadmap(project=project, date=today, items=items)

    slug = project.strip().lower().replace(" ", "-") or "project"
    constitution_ref = put_artifact(project_id, "docs/pdlc/memory/CONSTITUTION.md", constitution_md)
    intent_ref = put_artifact(project_id, "docs/pdlc/memory/INTENT.md", intent_md)
    roadmap_ref = put_artifact(project_id, f"docs/pdlc/memory/ROADMAP_{slug}_{today}.md", roadmap_md)

    return {
        "constitution_ref": constitution_ref,
        "intent_ref": intent_ref,
        "roadmap_ref": roadmap_ref,
    }


@instrumented_node("subphase.exited")
def init_gate(state: PDLCState) -> dict:
    """Open the init_approve gate; on approval, advance the phase to Inception."""
    payload = {
        "feature": state.get("feature"),
        "project_name": state.get("project_name"),
        "constitution_ref": state.get("constitution_ref"),
        "intent_ref": state.get("intent_ref"),
        "roadmap_ref": state.get("roadmap_ref"),
        "summary": "Constitution, Intent, and seed Roadmap ready — approve to begin Inception.",
    }
    verdict = gates.approval_gate(state, GATE_KIND, payload)
    approved = bool(verdict.get("approved"))
    out: dict = {"init_approved": approved}
    if approved:
        out["phase"] = "Inception"  # meta-graph routes the next turn to brainstorm
    return out


def build_init() -> StateGraph:
    """Uncompiled Initialization graph (START..gather..author..gate..END)."""
    g = StateGraph(PDLCState)
    g.add_node("gather", gather)
    g.add_node("author", author)
    g.add_node("init_gate", init_gate)
    g.add_edge(START, "gather")
    g.add_edge("gather", "author")
    g.add_edge("author", "init_gate")
    g.add_edge("init_gate", END)
    return g


init_graph = build_init().compile()
