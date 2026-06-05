"""DEFINE sub-phase (upstream skills/brainstorm/steps/02-define.md, steps 7-8).

Step 7 — read the full `brainstorm_log`, have Atlas draft each PRD section's
prose, assemble a deterministic PRD with `render_prd`, persist it via
`put_artifact`, and stash the uri in `prd_ref`.

Step 8 — open the `prd_approve` gate; record the verdict into `prd_approved`.

Graph shape: START -> define_prd -> prd_gate -> END. Compiled without a
checkpointer for composition; tests compile with a MemorySaver.
"""

from __future__ import annotations

from datetime import date as _date

from langgraph.graph import END, START, StateGraph

from ... import gates
from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...ports import put_artifact
from ...render import render_prd
from ...state import PDLCState

GATE_KIND = "prd_approve"


def _log_text(brainstorm_log: list[dict]) -> str:
    """Flatten the brainstorm log into a single prompt context block."""
    parts: list[str] = []
    for entry in brainstorm_log or []:
        section = entry.get("section") or entry.get("step") or "note"
        body = (entry.get("body") or "").strip()
        if body:
            parts.append(f"## {section}\n{body}")
    return "\n\n".join(parts) if parts else "_(empty brainstorm log)_"


def _draft(persona: str, section: str, feature: str, log: str) -> str:
    """One Atlas completion drafting a single PRD section from the log."""
    prompt = (
        f"You are drafting the '{section}' section of a PRD for the feature "
        f"'{feature}'. Synthesize from the full brainstorm log below; be "
        f"concrete and testable.\n\nBRAINSTORM LOG:\n{log}"
    )
    return complete(persona, prompt, system="PDLC PRD author").strip()


@instrumented_node("subphase.entered")
def define_prd(state: PDLCState) -> dict:
    """Step 7 — synthesize and persist the PRD draft."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    log = _log_text(state.get("brainstorm_log") or [])
    today = _date.today().isoformat()

    overview = _draft("atlas", "Overview", feature, log)
    problem_statement = _draft("atlas", "Problem Statement", feature, log)
    target_user = _draft("atlas", "Target User", feature, log)

    # The remaining sections reuse Atlas's drafting but are structured by the
    # renderer; the stub completion gives deterministic, log-derived prose.
    requirements = {
        "must": [_draft("atlas", "Requirement (MUST)", feature, log)],
        "should": [_draft("atlas", "Requirement (SHOULD)", feature, log)],
        "may": [],
    }
    assumptions = [_draft("atlas", "Assumptions", feature, log)]
    acceptance_criteria = [_draft("atlas", "Acceptance Criteria", feature, log)]
    user_stories = [
        {
            "id": "US-001",
            "title": _draft("atlas", "User Story title", feature, log),
            "acceptance": "1",
            "given": _draft("atlas", "User Story given", feature, log),
            "when": _draft("atlas", "User Story when", feature, log),
            "then": _draft("atlas", "User Story then", feature, log),
        }
    ]
    non_functional = [_draft("atlas", "Non-Functional Requirements", feature, log)]
    known_risks = [_draft("atlas", "Known Risks", feature, log)]
    out_of_scope = [_draft("atlas", "Out of Scope", feature, log)]

    prd_md = render_prd(
        feature=feature,
        date=today,
        status="Draft",
        overview=overview,
        problem_statement=problem_statement,
        target_user=target_user,
        requirements=requirements,
        assumptions=assumptions,
        acceptance_criteria=acceptance_criteria,
        user_stories=user_stories,
        non_functional=non_functional,
        known_risks=known_risks,
        out_of_scope=out_of_scope,
    )

    slug = feature.strip().lower().replace(" ", "-")
    path = f"docs/pdlc/prds/PRD_{slug}_{today}.md"
    prd_ref = put_artifact(project_id, path, prd_md)
    return {"prd_ref": prd_ref}


@instrumented_node("subphase.exited")
def prd_gate(state: PDLCState) -> dict:
    """Step 8 — open the PRD approval gate; record the verdict."""
    payload = {
        "feature": state.get("feature"),
        "prd_ref": state.get("prd_ref"),
        "summary": "PRD draft ready for review.",
    }
    verdict = gates.approval_gate(state, GATE_KIND, payload)
    return {"prd_approved": bool(verdict.get("approved"))}


def build_define() -> StateGraph:
    """Uncompiled DEFINE graph over PDLCState (START..steps..gate..END)."""
    g = StateGraph(PDLCState)
    g.add_node("define_prd", define_prd)
    g.add_node("prd_gate", prd_gate)
    g.add_edge(START, "define_prd")
    g.add_edge("define_prd", "prd_gate")
    g.add_edge("prd_gate", END)
    return g


define_graph = build_define().compile()
