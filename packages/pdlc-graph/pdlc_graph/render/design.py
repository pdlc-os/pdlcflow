"""Pure markdown renderers for the DESIGN sub-phase artifacts.

Five renderers, one per design artifact (upstream Brainstorm steps 10/10.5/10.6):

- `render_architecture`   -> ARCHITECTURE.md
- `render_data_model`     -> data-model.md
- `render_api_contracts`  -> api-contracts.md
- `render_threat_model`   -> threat-model.md   (template v1.0.0)
- `render_ux_review`      -> ux-review.md       (template v1.5.0)

Each is a pure (kwargs -> str) transform with no I/O. Nodes call a renderer,
then `ports.put_artifact(...)` to persist the returned string.
"""

from __future__ import annotations


def _bullets(items: list[str] | None, *, empty: str = "_none_") -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {it}" for it in items]


def render_architecture(
    *,
    feature: str,
    prd_ref: str | None = None,
    summary: str = "",
    components: list[str] | None = None,
    integrations: list[str] | None = None,
    data_flow: list[str] | None = None,
    decisions: list[str] | None = None,
    mermaid: str | None = None,
) -> str:
    """Render ARCHITECTURE.md (upstream step 10 / 9a)."""
    lines: list[str] = []
    lines.append(f"# Architecture — {feature}")
    lines.append("")
    lines.append(f"**PRD:** {prd_ref or '_(unlinked)_'}")
    lines.append("")
    lines.append("## Overview")
    lines.append(summary or "_(no summary)_")
    lines.append("")
    lines.append("## Components")
    lines.extend(_bullets(components))
    lines.append("")
    lines.append("## Integrations")
    lines.extend(_bullets(integrations))
    lines.append("")
    lines.append("## Data Flow")
    lines.extend(_bullets(data_flow))
    lines.append("")
    lines.append("## Architectural Decisions")
    lines.extend(_bullets(decisions))
    lines.append("")
    lines.append("## Component Diagram")
    lines.append("```mermaid")
    lines.append(mermaid or "flowchart TD\n    user[User] --> feature[Feature]")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def render_data_model(
    *,
    feature: str,
    entities: list[dict] | None = None,
    migrations: list[str] | None = None,
    not_persisted: list[str] | None = None,
    mermaid: str | None = None,
) -> str:
    """Render data-model.md. `entities` is [{"name","fields":[...] }, ...]."""
    lines: list[str] = []
    lines.append(f"# Data Model — {feature}")
    lines.append("")
    if not entities:
        lines.append("No data model changes. This feature operates on existing schema.")
        lines.append("")
        return "\n".join(lines)
    lines.append("## Entities")
    for ent in entities:
        lines.append("")
        lines.append(f"### {ent.get('name', '?')}")
        for field in ent.get("fields", []) or []:
            lines.append(f"- {field}")
    lines.append("")
    lines.append("## Entity Diagram")
    lines.append("```mermaid")
    lines.append(mermaid or "erDiagram\n    ENTITY {\n        id pk\n    }")
    lines.append("```")
    lines.append("")
    lines.append("## Migration Notes")
    lines.extend(_bullets(migrations))
    lines.append("")
    lines.append("## Deliberately Not Persisted")
    lines.extend(_bullets(not_persisted))
    lines.append("")
    return "\n".join(lines)


def render_api_contracts(
    *,
    feature: str,
    endpoints: list[dict] | None = None,
    notes: str = "",
) -> str:
    """Render api-contracts.md. `endpoints` is [{"method","path","auth","summary"}, ...]."""
    lines: list[str] = []
    lines.append(f"# API Contracts — {feature}")
    lines.append("")
    if not endpoints:
        lines.append(
            notes or "No new API endpoints. This feature uses existing endpoints."
        )
        lines.append("")
        return "\n".join(lines)
    for ep in endpoints:
        lines.append(f"## `{ep.get('method', 'GET')} {ep.get('path', '/')}`")
        lines.append(f"- **Auth:** {ep.get('auth', 'required')}")
        lines.append(f"- **Summary:** {ep.get('summary', '')}")
        if ep.get("request"):
            lines.append(f"- **Request:** {ep['request']}")
        if ep.get("response"):
            lines.append(f"- **Response (200):** {ep['response']}")
        lines.append("")
    return "\n".join(lines)


def render_threat_model(
    *,
    feature: str,
    triage: str,
    convened: str = "",
    participants: list[str] | None = None,
    triage_answers: list[str] | None = None,
    threats: list[dict] | None = None,
    open_questions: list[str] | None = None,
    decision: str = "",
    mom_ref: str | None = None,
) -> str:
    """Render threat-model.md (upstream step 10.5; template v1.0.0).

    `triage` is "skip" | "lite" | "full". `threats` is
    [{"id","title","stride","severity","action"}, ...].
    """
    label = {"skip": "Skipped", "lite": "Lite", "full": "Full"}.get(triage, triage)
    lines: list[str] = []
    lines.append(f"# Threat Model — {feature}")
    lines.append("<!-- pdlc-template-version: 1.0.0 -->")
    lines.append("")
    lines.append(f"**Triage:** {label}")
    lines.append(f"**Convened:** {convened or '_(n/a)_'}")
    lines.append("**Lead:** Phantom (Security Reviewer)")
    parts = ", ".join(participants) if participants else "n/a"
    lines.append(f"**Participants:** {parts}")
    lines.append("**Status:** Pending human approval (Step 12)")
    if mom_ref:
        lines.append(f"**MOM:** {mom_ref}")
    lines.append("")
    lines.append("## Triage Record")
    questions = [
        "Does this feature introduce or modify a trust boundary?",
        "Does this feature touch regulated data (PII, payment, health)?",
        "Does this feature add a new attack surface?",
    ]
    answers = triage_answers or []
    lines.append("| Question | Answer |")
    lines.append("|---|---|")
    for i, q in enumerate(questions):
        ans = answers[i] if i < len(answers) else "no"
        lines.append(f"| {q} | {ans} |")
    lines.append("")
    lines.append(f"**Triage outcome:** {label}")
    lines.append("")
    if triage == "skip":
        lines.append("_Triage came out Skip — no trust boundaries warranted modeling._")
        lines.append("")
        return "\n".join(lines)
    lines.append("## Threats Identified")
    lines.append("")
    if not threats:
        lines.append("_No threats prioritized._")
    else:
        for t in threats:
            lines.append(f"### {t.get('id', 'T-000')} — {t.get('title', '')}")
            lines.append(f"- **STRIDE category:** {t.get('stride', '')}")
            lines.append(f"- **Severity:** {t.get('severity', '')}")
            lines.append(f"- **Proposed action:** {t.get('action', '')}")
            lines.append("")
    lines.append("## Open Questions for Human")
    if open_questions:
        lines.extend(f"{i + 1}. {q}" for i, q in enumerate(open_questions))
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Party Decision")
    lines.append(decision or "_deferred_")
    lines.append("")
    return "\n".join(lines)


def render_ux_review(
    *,
    feature: str,
    triage: str,
    convened: str = "",
    participants: list[str] | None = None,
    triage_answers: list[str] | None = None,
    findings: list[dict] | None = None,
    open_questions: list[str] | None = None,
    decision: str = "",
    mom_ref: str | None = None,
) -> str:
    """Render ux-review.md (upstream step 10.6; template v1.5.0).

    `triage` is "skip" | "lite" | "full". `findings` is
    [{"id","title","severity","action"}, ...].
    """
    label = {"skip": "Skipped", "lite": "Lite", "full": "Full"}.get(triage, triage)
    lines: list[str] = []
    lines.append(f"# UX Review — {feature}")
    lines.append("<!-- pdlc-template-version: 1.5.0 -->")
    lines.append("")
    lines.append(f"**Triage:** {label}")
    lines.append(f"**Convened:** {convened or '_(n/a)_'}")
    lines.append("**Lead:** Muse (UX Designer)")
    parts = ", ".join(participants) if participants else "n/a"
    lines.append(f"**Participants:** {parts}")
    lines.append("**Status:** Pending human approval (Step 12)")
    if mom_ref:
        lines.append(f"**MOM:** {mom_ref}")
    lines.append("")
    lines.append("## Triage Record")
    questions = [
        "Does this feature add or modify any user-facing UI surface?",
        "Does this feature introduce a new flow, page, or interaction pattern?",
        "Does this feature touch first-experience pathways (onboarding, signup)?",
    ]
    answers = triage_answers or []
    lines.append("| Question | Answer |")
    lines.append("|---|---|")
    for i, q in enumerate(questions):
        ans = answers[i] if i < len(answers) else "no"
        lines.append(f"| {q} | {ans} |")
    lines.append("")
    lines.append(f"**Triage outcome:** {label}")
    lines.append("")
    if triage == "skip":
        lines.append("_Triage came out Skip — no user-facing surface warranted an audit._")
        lines.append("")
        return "\n".join(lines)
    lines.append("## Findings & Proposed Actions")
    lines.append("")
    if not findings:
        lines.append("_No findings surfaced._")
    else:
        for f in findings:
            lines.append(f"### {f.get('id', 'F-000')} — {f.get('title', '')}")
            lines.append(f"- **Severity:** {f.get('severity', '')}")
            lines.append(f"- **Proposed action:** {f.get('action', '')}")
            lines.append("")
    lines.append("## Open Questions for Human")
    if open_questions:
        lines.extend(f"{i + 1}. {q}" for i, q in enumerate(open_questions))
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Roundtable Decision")
    lines.append(decision or "_deferred_")
    lines.append("")
    return "\n".join(lines)
