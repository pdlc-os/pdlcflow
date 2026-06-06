"""DESIGN sub-phase (upstream skills/brainstorm/steps/03-design.md, steps 9-12).

Node chain (START..steps..gate..END):

  9    create_design_dir  — set `design_dir` (subphase.entered).
  9a   blooms_design      — Bloom's Taxonomy questioning, 3 rounds
                            (Mechanics -> Apply -> Trade-offs) via `interaction.ask`,
                            Neo leads. One ask() == one round.
  10   generate_docs      — render ARCHITECTURE / data-model / api-contracts via the
                            pure renderers in render/design.py; persist each; set
                            `design_docs`.
  10.5 threat_model       — Phantom triage (skip/lite/full); on lite/full convene a
                            `threat-model` party (Phantom + team); render & persist
                            `threat-model.md`; set `threat_model_ref`.
  10.6 design_laws        — Muse triage (skip/lite/full); on lite/full convene a
                            `design-laws` Roundtable (Muse + team); render & persist
                            `ux-review.md`; set `ux_review_ref`.
  11   update_links       — fold all five artifact links into `design_docs`
                            (subphase.exited).
  12   design_gate        — open the `design_docs_approve` gate; record
                            `design_approved`.

Triage signals are read from simple state flags (defaulting so the Full path is
exercisable). Compiled without a checkpointer for composition; tests compile
with a MemorySaver.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ... import gates
from ...instrumentation import evaluate, instrumented_node
from ...interaction import ask
from ...llm_port import complete
from ...ports import get_artifact, put_artifact
from ...render import (
    render_api_contracts,
    render_architecture,
    render_data_model,
    render_threat_model,
    render_ux_review,
)
from ...state import PDLCState
from ..parties import run_party, triage_level

GATE_KIND = "design_docs_approve"

# Bloom's Taxonomy design rounds (Neo leads). Mechanics -> Apply -> Trade-offs.
_BLOOMS_ROUNDS: list[tuple[str, list[str]]] = [
    (
        "Mechanics",
        [
            "Walk me through the data flow for the primary journey — what is read, "
            "written, and in what order?",
            "What happens when the user takes the key action while a concurrent "
            "condition is in play?",
        ],
    ),
    (
        "Apply",
        [
            "Given your tech stack, which layer handles the core responsibility — "
            "client, API, service, or database?",
            "Which existing patterns, utilities, or base classes should this extend "
            "rather than build from scratch?",
        ],
    ),
    (
        "Trade-offs",
        [
            "Where are the natural component boundaries and the highest-stakes "
            "failure mode?",
            "If we had to cut one aspect to ship faster — simplicity, flexibility, "
            "or consistency — what would you sacrifice?",
        ],
    ),
]


def _slug(feature: str) -> str:
    return feature.strip().lower().replace(" ", "-") or "feature"


def _triage_signals(state: PDLCState, key: str, default: list[bool]) -> list[bool]:
    """Read a 3-item triage checklist from the declared state field `key`
    (`threat_signals` or `ux_signals`). Absent -> `default`, which keeps a
    couple of signals True so the Full party path stays exercisable.
    """
    sig = state.get(key)
    if sig is None:
        return default
    return [bool(x) for x in sig]


@instrumented_node("subphase.entered")
def create_design_dir(state: PDLCState) -> dict:
    """Step 9 — establish the per-feature design directory."""
    feature = state.get("feature") or "untitled-feature"
    return {"design_dir": f"docs/pdlc/design/{_slug(feature)}"}


@instrumented_node("step.completed")
def blooms_design(state: PDLCState) -> dict:
    """Step 9a — Neo-led Bloom's Taxonomy questioning across three rounds.

    Each round is a single `ask()` (one interrupt). Under night-shift the
    drafts are auto-accepted with no human turn.
    """
    feature = state.get("feature") or "untitled-feature"
    captured: list[dict] = []
    for name, questions in _BLOOMS_ROUNDS:
        drafts = [
            complete(
                "neo",
                f"Bloom's design round '{name}' for feature '{feature}'. Q: {q}",
                system="PDLC architect (Neo)",
            ).strip()
            for q in questions
        ]
        result = ask(
            state,
            questions,
            drafts=drafts,
            context=f"Design Discovery (Bloom's Taxonomy) — Round: {name}",
        )
        captured.append(
            {"round": name, "questions": questions, "answers": result.get("answers", [])}
        )

    existing = list(state.get("brainstorm_log") or [])
    body_lines: list[str] = []
    for rnd in captured:
        body_lines.append(f"### Round — {rnd['round']}")
        for q, a in zip(rnd["questions"], rnd["answers"], strict=False):
            body_lines.append(f"- **Q:** {q}\n  **A:** {a}")
    entry = {
        "section": "Design Discovery (Bloom's Taxonomy)",
        "body": "\n".join(body_lines),
        "rounds": captured,
    }
    return {"brainstorm_log": [*existing, entry]}


@instrumented_node("step.completed")
def generate_docs(state: PDLCState) -> dict:
    """Step 10 — render and persist the three core design documents."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    design_dir = state.get("design_dir") or f"docs/pdlc/design/{_slug(feature)}"
    prd_ref = state.get("prd_ref")

    summary = complete(
        "neo",
        f"One-paragraph architecture overview for feature '{feature}'.",
        system="PDLC architect (Neo)",
    ).strip()

    architecture = render_architecture(
        feature=feature,
        prd_ref=prd_ref,
        summary=summary,
        components=[f"{feature} service module", "existing API gateway"],
        integrations=["existing auth layer", "primary datastore"],
        data_flow=["request enters API", "service validates + persists", "response returned"],
        decisions=[
            complete(
                "neo",
                f"State one architectural decision (with rationale) for '{feature}'.",
                system="PDLC architect (Neo)",
            ).strip()
        ],
    )
    arch_uri = put_artifact(project_id, f"{design_dir}/ARCHITECTURE.md", architecture)

    data_model = render_data_model(
        feature=feature,
        entities=[
            {
                "name": f"{_slug(feature)}_record",
                "fields": ["id: uuid (pk)", "created_at: timestamptz", "payload: jsonb"],
            }
        ],
        migrations=[f"create_{_slug(feature)}_table"],
    )
    dm_uri = put_artifact(project_id, f"{design_dir}/data-model.md", data_model)

    api_contracts = render_api_contracts(
        feature=feature,
        endpoints=[
            {
                "method": "POST",
                "path": f"/api/{_slug(feature)}",
                "auth": "required (bearer)",
                "summary": f"Create a {feature} record",
                "request": "{ payload: object }",
                "response": "{ id: uuid }",
            }
        ],
    )
    api_uri = put_artifact(project_id, f"{design_dir}/api-contracts.md", api_contracts)

    # Phase J: score the design output (no-op unless evals enabled). Grounded in
    # the architecture doc + the PRD (the latter drives the spec_adherence eval).
    _sources = {"architecture": architecture, "feature": feature}
    prd_ref = state.get("prd_ref")
    if prd_ref:
        try:
            _sources["PRD"] = get_artifact(prd_ref)
        except Exception:  # artifact unavailable — spec_adherence falls back to n/a
            pass
    evaluate(
        "design_docs", state, "\n".join([architecture, data_model, api_contracts]),
        target="neo", sources=_sources,
    )

    return {
        "design_docs": {
            "architecture": arch_uri,
            "data_model": dm_uri,
            "api_contracts": api_uri,
        }
    }


@instrumented_node("step.completed")
def threat_model(state: PDLCState) -> dict:
    """Step 10.5 — Phantom triage; convene a threat-model party on lite/full."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    design_dir = state.get("design_dir") or f"docs/pdlc/design/{_slug(feature)}"

    signals = _triage_signals(state, "threat_signals", [True, True, False])
    triage_answers = ["yes" if s else "no" for s in signals]
    level = triage_level(signals)

    mom_ref: str | None = None
    decision = ""
    participants: list[str] = []
    threats: list[dict] = []
    if level in ("lite", "full"):
        roster = ["phantom"] if level == "lite" else ["phantom", "neo", "bolt", "atlas"]
        party = run_party(
            feature=feature,
            project_id=project_id,
            kind="threat-model",
            topic="Pressure-test the design for security threats",
            roster=roster,
            context="Design docs generated; walk the trust boundaries.",
            night_shift_active=bool(state.get("night_shift_active")),
        )
        mom_ref = party.get("mom_ref")
        decision = party.get("decision", "")
        participants = roster
        threats = [
            {
                "id": "T-001",
                "title": "Unauthorized record access across tenant boundary",
                "stride": "Information Disclosure",
                "severity": "HIGH",
                "action": "Mitigate now",
            }
        ]

    content = render_threat_model(
        feature=feature,
        triage=level,
        participants=participants,
        triage_answers=triage_answers,
        threats=threats,
        open_questions=["What is the threat-actor profile for this feature?"]
        if level == "full"
        else None,
        decision=decision,
        mom_ref=mom_ref,
    )
    uri = put_artifact(project_id, f"{design_dir}/threat-model.md", content)
    return {"threat_model_ref": uri}


@instrumented_node("step.completed")
def design_laws(state: PDLCState) -> dict:
    """Step 10.6 — Muse triage; convene a design-laws Roundtable on lite/full."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    design_dir = state.get("design_dir") or f"docs/pdlc/design/{_slug(feature)}"

    signals = _triage_signals(state, "ux_signals", [True, True, False])
    triage_answers = ["yes" if s else "no" for s in signals]
    level = triage_level(signals)

    mom_ref: str | None = None
    decision = ""
    participants: list[str] = []
    findings: list[dict] = []
    if level in ("lite", "full"):
        roster = ["muse"] if level == "lite" else ["muse", "neo", "echo", "phantom"]
        party = run_party(
            feature=feature,
            project_id=project_id,
            kind="design-laws",
            topic="Audit the user-facing surface against the design laws",
            roster=roster,
            context="Design docs + threat model in place; run the heuristics.",
            night_shift_active=bool(state.get("night_shift_active")),
        )
        mom_ref = party.get("mom_ref")
        decision = party.get("decision", "")
        participants = roster
        findings = [
            {
                "id": "F-001",
                "title": "No visible focus state on the primary action",
                "severity": "P1",
                "action": "Fix now",
            }
        ]

    content = render_ux_review(
        feature=feature,
        triage=level,
        participants=participants,
        triage_answers=triage_answers,
        findings=findings,
        open_questions=["Is the keyboard-only path a hard requirement here?"]
        if level == "full"
        else None,
        decision=decision,
        mom_ref=mom_ref,
    )
    uri = put_artifact(project_id, f"{design_dir}/ux-review.md", content)
    return {"ux_review_ref": uri}


@instrumented_node("subphase.exited")
def update_links(state: PDLCState) -> dict:
    """Step 11 — fold all five artifact links into `design_docs`."""
    docs = dict(state.get("design_docs") or {})
    if state.get("threat_model_ref"):
        docs["threat_model"] = state["threat_model_ref"]
    if state.get("ux_review_ref"):
        docs["ux_review"] = state["ux_review_ref"]
    return {"design_docs": docs}


@instrumented_node("step.completed")
def design_gate(state: PDLCState) -> dict:
    """Step 12 — open the design approval gate; record the verdict."""
    payload = {
        "feature": state.get("feature"),
        "design_dir": state.get("design_dir"),
        "design_docs": state.get("design_docs"),
        "threat_model_ref": state.get("threat_model_ref"),
        "ux_review_ref": state.get("ux_review_ref"),
        "summary": "Design package (5 artifacts) ready for review.",
    }
    verdict = gates.approval_gate(state, GATE_KIND, payload)
    return {"design_approved": bool(verdict.get("approved"))}


def build_design() -> StateGraph:
    """Uncompiled DESIGN graph over PDLCState (START..steps..gate..END)."""
    g = StateGraph(PDLCState)
    g.add_node("create_design_dir", create_design_dir)
    g.add_node("blooms_design", blooms_design)
    g.add_node("generate_docs", generate_docs)
    g.add_node("threat_model", threat_model)
    g.add_node("design_laws", design_laws)
    g.add_node("update_links", update_links)
    g.add_node("design_gate", design_gate)
    g.add_edge(START, "create_design_dir")
    g.add_edge("create_design_dir", "blooms_design")
    g.add_edge("blooms_design", "generate_docs")
    g.add_edge("generate_docs", "threat_model")
    g.add_edge("threat_model", "design_laws")
    g.add_edge("design_laws", "update_links")
    g.add_edge("update_links", "design_gate")
    g.add_edge("design_gate", END)
    return g


design_graph = build_design().compile()
