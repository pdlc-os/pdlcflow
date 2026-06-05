"""PRD renderer — upstream templates/PRD.md shape.

Assembles a complete Product Requirements Document from already-drafted
section prose into deterministic markdown. Pure function: no I/O, no model.
Nodes draft prose with `llm_port.complete(persona="atlas", ...)`, then call
this to lay out the document and `ports.put_artifact(...)` to persist it.
"""

from __future__ import annotations


def _bullets(items: list[str] | None, *, empty: str = "_(none)_") -> list[str]:
    items = [i.strip() for i in (items or []) if i and i.strip()]
    if not items:
        return [empty]
    return [f"- {i}" for i in items]


def _numbered(items: list[str] | None, *, empty: str = "_(none)_") -> list[str]:
    items = [i.strip() for i in (items or []) if i and i.strip()]
    if not items:
        return [empty]
    return [f"{n}. {i}" for n, i in enumerate(items, start=1)]


def _requirements_block(requirements: dict | None) -> list[str]:
    """`requirements` is {"must": [...], "should": [...], "may": [...]}.

    Rendered as a single RFC-2119 numbered list with the priority verb
    interpolated, preserving MUST → SHOULD → MAY order.
    """
    requirements = requirements or {}
    flat: list[str] = []
    for level in ("must", "should", "may"):
        verb = level.upper()
        for text in requirements.get(level, []) or []:
            text = text.strip()
            if not text:
                continue
            flat.append(f"The system {verb} {text}")
    return _numbered(flat, empty="_(no requirements captured)_")


def _user_stories_block(stories: list[dict] | None) -> list[str]:
    """`stories` is [{"id","title","acceptance","given","when","then"}, ...]."""
    lines: list[str] = []
    if not stories:
        return ["_(no user stories captured)_"]
    for s in stories:
        sid = s.get("id", "US-???")
        title = s.get("title", "").strip() or "[untitled]"
        ac = s.get("acceptance", "")
        lines.append(f"**{sid}: {title}**")
        lines.append(f"*Acceptance criteria: {ac}*")
        lines.append(f"Given {s.get('given', '').strip()}")
        lines.append(f"When {s.get('when', '').strip()}")
        lines.append(f"Then {s.get('then', '').strip()}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def render_prd(
    *,
    feature: str,
    date: str,
    slug: str | None = None,
    status: str = "Draft",
    overview: str = "",
    problem_statement: str = "",
    target_user: str = "",
    requirements: dict | None = None,
    assumptions: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    user_stories: list[dict] | None = None,
    non_functional: list[str] | None = None,
    known_risks: list[str] | None = None,
    out_of_scope: list[str] | None = None,
    approved_by: str | None = None,
    approved_date: str | None = None,
    approval_notes: str | None = None,
) -> str:
    """Render a PRD to markdown. Deterministic in its inputs."""
    slug = slug or feature.strip().lower().replace(" ", "-")
    L: list[str] = []

    L.append(f"# PRD: {feature}")
    L.append("")
    L.append(f"**Date:** {date}")
    L.append(f"**Status:** {status}")
    L.append(f"**Feature slug:** {slug}")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Overview")
    L.append("")
    L.append(overview.strip() or "_(to be drafted)_")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Problem Statement")
    L.append("")
    L.append(problem_statement.strip() or "_(to be drafted)_")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Target User")
    L.append("")
    L.append(target_user.strip() or "_(to be drafted)_")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Requirements")
    L.append("")
    L.extend(_requirements_block(requirements))
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Assumptions")
    L.append("")
    L.extend(_bullets(assumptions, empty="_(none captured)_"))
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Acceptance Criteria")
    L.append("")
    L.extend(_numbered(acceptance_criteria, empty="_(none captured)_"))
    L.append("")
    L.append("---")
    L.append("")

    L.append("## User Stories")
    L.append("")
    L.extend(_user_stories_block(user_stories))
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Non-Functional Requirements")
    L.append("")
    L.extend(_bullets(non_functional, empty="_(none captured)_"))
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Known Risks")
    L.append("")
    L.extend(_bullets(known_risks, empty="_(none captured)_"))
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Out of Scope")
    L.append("")
    L.extend(_bullets(out_of_scope, empty="_(none captured)_"))
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Design Docs")
    L.append("")
    L.append("<!-- Auto-populated after the Design sub-phase. -->")
    L.append("- Architecture: _(pending Design)_")
    L.append("- Data model: _(pending Design)_")
    L.append("- API contracts: _(pending Design)_")
    L.append("- Threat model: _(pending Design)_")
    L.append("- UX review: _(pending Design)_")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Approval")
    L.append("")
    L.append(f"**Approved by:** {approved_by or '_(pending)_'}")
    L.append(f"**Date approved:** {approved_date or '_(pending)_'}")
    L.append(f"**Notes:** {approval_notes or '_(none)_'}")
    L.append("")

    return "\n".join(L)
