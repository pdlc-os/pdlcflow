"""DISCOVER sub-phase (upstream skills/brainstorm/steps/01-discover.md, steps 0-6).

Models the real Discover steps as graph nodes:

- Step 0  — divergent ideation (optional): `complete()` synthesizes candidate
            ideas into the brainstorm log when a `divergent_ideation` signal is set.
- Step 2  — Socratic discovery: 3 rounds (Problem -> Future State -> Acceptance
            Criteria) via `interaction.ask()`, one round per `ask()`.
- Step 2a — Progressive thinking: a `run_party` agent-team meeting (Atlas + 8),
            ALWAYS run; result stashed in `party_results["progressive-thinking"]`.
- Step 3  — Adversarial review: Atlas `complete()` produces >=10 findings.
- Step 4  — Edge-case analysis: `complete()` traces paths, triages each entry.
- Step 4.5— UX discovery: CONDITIONAL on a `visual` signal; Muse leads via `ask()`.
- Steps 5-6 — Synthesis: render + persist the discovery summary, set
            `discovery_summary`, then open the `discover_summary` approval gate.

Each step appends a `{"section", "body", "step"}` dict to `brainstorm_log`.
`brainstorm_log` has no reducer, so every node reads the existing list and
returns the full new list. The gate verdict is recorded into `party_results`
(there is no dedicated `discover_approved` field on PDLCState).

Graph shape: START -> divergent_ideation -> socratic_discovery ->
progressive_thinking -> adversarial_review -> edge_case_analysis ->
(ux_discovery?) -> synthesis -> discover_gate -> END. Compiled without a
checkpointer for composition; tests compile with a MemorySaver.
"""

from __future__ import annotations

from datetime import date as _date

from langgraph.graph import END, START, StateGraph

from ... import gates, interaction
from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...ports import put_artifact
from ...render import render_discovery_summary
from ...state import PDLCState
from ...visual import options_screen, visual
from ..parties import run_party

GATE_KIND = "discover_summary"

# Atlas facilitates; 8 other agents pitch (upstream 06-progressive-thinking.md).
PROGRESSIVE_ROSTER = [
    "atlas",
    "neo",
    "echo",
    "phantom",
    "bolt",
    "friday",
    "muse",
    "pulse",
    "jarvis",
]

# Socratic interview: 3 rounds, <=4 questions each (upstream 01-socratic-discovery.md).
SOCRATIC_ROUNDS: list[tuple[str, list[str]]] = [
    (
        "Problem Statement",
        [
            "What problem does this specific feature solve?",
            "Who specifically will use this feature, and in what context?",
            "What does success look like? What metric moves, and by how much?",
            "What are the technical constraints or dependencies for this feature?",
        ],
    ),
    (
        "Future State / Key Capabilities",
        [
            "What are the key capabilities this feature must deliver?",
            "What does the end-to-end happy path look like?",
            "What existing components or services does it compose?",
        ],
    ),
    (
        "Acceptance Criteria",
        [
            "How will we verify the feature works? What is the definition of done?",
            "What measurable signals confirm the success metric was hit?",
        ],
    ),
]

# Adversarial review dimensions (upstream 02-adversarial-review.md) — one finding each.
ADVERSARIAL_DIMENSIONS = [
    "Assumption gaps",
    "Scope leaks",
    "Success metric fragility",
    "Technical risk blindspots",
    "User problem validity",
    "Dependency blindspots",
    "Edge case silence",
    "Requirement conflicts",
    "Definition-of-done gaps",
    "Timeline and sizing naivety",
]

# Edge-case categories (upstream 03-edge-case-analysis.md).
EDGE_CASE_CATEGORIES = [
    "User flow branches",
    "Empty and boundary data",
    "Invalid and malformed inputs",
    "Permission and access boundaries",
    "Concurrency and timing",
    "Integration failure modes",
]

_TRIAGE_BUCKETS = ("in scope", "out of scope", "known risk")


def _log(state: PDLCState) -> list[dict]:
    """Snapshot the current brainstorm log (no reducer — caller returns full list)."""
    return list(state.get("brainstorm_log") or [])


def _has_visual_signal(state: PDLCState) -> bool:
    """True when the feature carries a visual/UI signal (gates UX Discovery)."""
    if state.get("visual"):
        return True
    domains = state.get("domains") or []
    return any(d in ("visual", "ui", "ux") for d in domains)


@instrumented_node("subphase.entered")
def divergent_ideation(state: PDLCState) -> dict:
    """Step 0 — optional divergent ideation; synthesize candidate ideas."""
    log = _log(state)
    if not state.get("enable_divergent_ideation"):
        return {"brainstorm_log": log}

    feature = state.get("feature") or "untitled-feature"
    ideas = []
    for lens in ("Technical", "User Experience", "Business", "Edge Cases"):
        prompt = (
            f"Divergent ideation for '{feature}' through the {lens} lens. "
            f"Propose one unexpected candidate idea."
        )
        ideas.append(f"- ({lens}) {complete('muse', prompt).strip()}")
    body = "Candidate ideas (domain rotation):\n" + "\n".join(ideas)
    log.append({"section": "Divergent Ideation", "body": body, "step": "divergent-ideation"})
    return {"brainstorm_log": log}


@instrumented_node("step.completed")
def socratic_discovery(state: PDLCState) -> dict:
    """Step 2 — three Socratic rounds via interaction.ask (one round per ask)."""
    feature = state.get("feature") or "untitled-feature"
    parts: list[str] = []
    for title, questions in SOCRATIC_ROUNDS:
        drafts = [
            complete(
                "atlas",
                f"Draft an answer for '{feature}' to: {q}",
                system="PDLC discovery interviewer",
            ).strip()
            for q in questions
        ]
        result = interaction.ask(
            state,
            questions,
            drafts=drafts,
            context=f"Socratic round — {title}",
        )
        answers = result.get("answers") or []
        parts.append(f"### Round — {title}")
        for i, q in enumerate(questions):
            ans = answers[i] if i < len(answers) else ""
            parts.append(f"**Q:** {q}\n**A:** {ans or '_(no answer)_'}")
    log = _log(state)
    log.append(
        {
            "section": "Socratic Discovery",
            "body": "\n\n".join(parts),
            "step": "socratic-discovery",
        }
    )
    return {"brainstorm_log": log}


@instrumented_node("step.completed")
def progressive_thinking(state: PDLCState) -> dict:
    """Step 2a — ALWAYS-run progressive-thinking agent-team meeting (Atlas + 8)."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    result = run_party(
        feature=feature,
        project_id=project_id,
        kind="progressive-thinking",
        topic=(
            "Pressure-test the discovery: confirmed facts, inferences, "
            "consequences, risks, conflicts, and design priorities."
        ),
        roster=PROGRESSIVE_ROSTER,
        context="Progressive thinking refinement of the Discover findings.",
        night_shift_active=bool(state.get("night_shift_active")),
    )
    body = (
        f"**MOM:** {result.get('mom_ref')}\n"
        f"**Decision:** {result.get('decision')}\n"
        f"**Participants:** {', '.join(PROGRESSIVE_ROSTER)}"
    )
    log = _log(state)
    log.append(
        {
            "section": "Progressive Thinking (Agent Team Meeting)",
            "body": body,
            "step": "progressive-thinking",
        }
    )
    party_results = dict(state.get("party_results") or {})
    party_results["progressive-thinking"] = result
    return {"brainstorm_log": log, "party_results": party_results}


@instrumented_node("step.completed")
def adversarial_review(state: PDLCState) -> dict:
    """Step 3 — Atlas (devil's advocate) surfaces >=10 findings."""
    feature = state.get("feature") or "untitled-feature"
    findings: list[str] = []
    for i, dim in enumerate(ADVERSARIAL_DIMENSIONS, start=1):
        prompt = (
            f"Adversarial review of '{feature}'. Dimension: {dim}. "
            f"State the single most damaging gap a skeptic would raise."
        )
        findings.append(f"{i}. [{dim}] {complete('atlas', prompt).strip()}")
    body = "### Findings\n" + "\n".join(findings)
    log = _log(state)
    log.append({"section": "Adversarial Review", "body": body, "step": "adversarial-review"})
    return {"brainstorm_log": log}


@instrumented_node("step.completed")
def edge_case_analysis(state: PDLCState) -> dict:
    """Step 4 — trace branching paths and triage each into a bucket."""
    feature = state.get("feature") or "untitled-feature"
    rows: list[str] = ["| # | Category | Scenario | Addressed? | Triage |", "|---|---|---|---|---|"]
    for i, cat in enumerate(EDGE_CASE_CATEGORIES, start=1):
        prompt = (
            f"Edge-case path trace for '{feature}'. Category: {cat}. "
            f"Describe one unhandled scenario in a single sentence."
        )
        scenario = complete("echo", prompt).strip().replace("\n", " ")
        bucket = _TRIAGE_BUCKETS[i % len(_TRIAGE_BUCKETS)]
        rows.append(f"| {i} | {cat} | {scenario} | No | {bucket} |")
    body = "### Findings & triage\n" + "\n".join(rows)
    log = _log(state)
    log.append({"section": "Edge Case Analysis", "body": body, "step": "edge-case-analysis"})
    return {"brainstorm_log": log}


@instrumented_node("step.completed")
def ux_discovery(state: PDLCState) -> dict:
    """Step 4.5 — conditional UX round; Muse leads via interaction.ask."""
    feature = state.get("feature") or "untitled-feature"
    questions = [
        "Look and feel: which layout / information hierarchy fits this feature?",
        "Flow: how should the user move across screens?",
        "State coverage: how should empty / loading / error / success read?",
    ]
    drafts = [
        complete(
            "muse",
            f"Propose a UX answer for '{feature}', grounded in existing patterns: {q}",
            system="PDLC UX designer",
        ).strip()
        for q in questions
    ]
    # Visual companion: one option-screen per question, drawn beside the chat.
    companion = visual(
        [
            options_screen(
                "Look & feel",
                [
                    {"title": "Sidebar + card grid", "description": "Reuses the /dashboard shell"},
                    {"title": "Full-width + top nav", "description": "Reuses the /settings shell"},
                ],
                subtitle="Which layout fits this feature?",
                key="q0",
            ),
            options_screen(
                "User flow",
                [
                    {"title": "Single screen", "description": "No navigation between steps"},
                    {"title": "Wizard / multi-step", "description": "Guided across screens"},
                ],
                subtitle="How should the user move through it?",
                key="q1",
            ),
            options_screen(
                "State coverage",
                [
                    {"title": "All four states", "description": "empty / loading / error / success"},
                    {"title": "Happy path only", "description": "success state for now"},
                ],
                subtitle="Which UI states must we cover?",
                key="q2",
            ),
        ]
    )
    result = interaction.ask(
        state,
        questions,
        drafts=drafts,
        context="UX Discovery — Muse leads, visual-first, grounded in the UI inventory.",
        visual=companion,
    )
    answers = result.get("answers") or []
    parts = ["**Lead:** Muse (UX Designer)"]
    for i, q in enumerate(questions):
        ans = answers[i] if i < len(answers) else ""
        parts.append(f"**Q:** {q}\n**A:** {ans or '_(no answer)_'}")
    log = _log(state)
    log.append(
        {"section": "UX Discovery", "body": "\n\n".join(parts), "step": "ux-discovery"}
    )
    return {"brainstorm_log": log}


@instrumented_node("step.completed")
def synthesis(state: PDLCState) -> dict:
    """Steps 5-6 — synthesize, render + persist the discovery summary."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    log = _log(state)
    today = _date.today().isoformat()
    context = "\n\n".join(
        f"## {e.get('section')}\n{e.get('body', '')}" for e in log
    ) or "_(empty brainstorm log)_"

    def _field(name: str) -> str:
        return complete(
            "atlas",
            f"From the Discover record below, state the '{name}' for '{feature}' "
            f"in one sentence.\n\n{context}",
            system="PDLC discovery synthesizer",
        ).strip()

    summary_md = render_discovery_summary(
        feature=feature,
        date=today,
        problem=_field("problem"),
        user=_field("target user and context"),
        success_metric=_field("success metric"),
        technical_constraints=[_field("technical constraint")],
        out_of_scope=[_field("out-of-scope item")],
        risks=[_field("key risk or assumption")],
        log_sections=[str(e.get("section")) for e in log],
    )
    slug = feature.strip().lower().replace(" ", "-")
    path = f"docs/pdlc/brainstorm/discovery_summary_{slug}_{today}.md"
    uri = put_artifact(project_id, path, summary_md)

    log.append(
        {
            "section": "Discovery Summary",
            "body": f"Persisted at {uri}",
            "step": "synthesis",
        }
    )
    return {"brainstorm_log": log, "discovery_summary": summary_md}


@instrumented_node("subphase.exited")
def discover_gate(state: PDLCState) -> dict:
    """Open the discover_summary approval gate; record the verdict."""
    payload = {
        "feature": state.get("feature"),
        "summary": "Discovery summary ready for review.",
        "discovery_summary": state.get("discovery_summary"),
    }
    verdict = gates.approval_gate(state, GATE_KIND, payload)
    party_results = dict(state.get("party_results") or {})
    party_results["discover_summary"] = {
        "approved": bool(verdict.get("approved")),
        "comment": verdict.get("comment"),
    }
    return {"party_results": party_results}


def _after_edge_cases(state: PDLCState) -> str:
    """Route to UX Discovery only when a visual signal is present."""
    return "ux_discovery" if _has_visual_signal(state) else "synthesis"


def build_discover() -> StateGraph:
    """Uncompiled DISCOVER graph over PDLCState (START..steps..gate..END)."""
    g = StateGraph(PDLCState)
    g.add_node("divergent_ideation", divergent_ideation)
    g.add_node("socratic_discovery", socratic_discovery)
    g.add_node("progressive_thinking", progressive_thinking)
    g.add_node("adversarial_review", adversarial_review)
    g.add_node("edge_case_analysis", edge_case_analysis)
    g.add_node("ux_discovery", ux_discovery)
    g.add_node("synthesis", synthesis)
    g.add_node("discover_gate", discover_gate)

    g.add_edge(START, "divergent_ideation")
    g.add_edge("divergent_ideation", "socratic_discovery")
    g.add_edge("socratic_discovery", "progressive_thinking")
    g.add_edge("progressive_thinking", "adversarial_review")
    g.add_edge("adversarial_review", "edge_case_analysis")
    g.add_conditional_edges(
        "edge_case_analysis", _after_edge_cases, ["ux_discovery", "synthesis"]
    )
    g.add_edge("ux_discovery", "synthesis")
    g.add_edge("synthesis", "discover_gate")
    g.add_edge("discover_gate", END)
    return g


discover_graph = build_discover().compile()
