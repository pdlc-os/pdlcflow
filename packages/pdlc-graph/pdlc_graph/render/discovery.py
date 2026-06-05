"""Discovery summary renderer — upstream brainstorm step 6 (`04-synthesis.md`).

Produces the `DISCOVERY SUMMARY` markdown that closes the Discover sub-phase
and feeds the PRD author. Pure (kwargs -> str) transform: no I/O.
"""

from __future__ import annotations


def _bullets(items: list[str] | None, *, empty: str = "_none_") -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {it}" for it in items]


def render_discovery_summary(
    *,
    feature: str,
    date: str,
    problem: str,
    user: str,
    success_metric: str,
    technical_constraints: list[str] | None = None,
    out_of_scope: list[str] | None = None,
    risks: list[str] | None = None,
    log_sections: list[str] | None = None,
) -> str:
    """Render the confirmed discovery summary (upstream Step 6 format)."""
    lines: list[str] = []
    lines.append(f"# Discovery Summary — {feature}")
    lines.append("")
    lines.append(f"**Date:** {date}")
    lines.append("**Status:** discover-complete")
    lines.append("")
    lines.append(f"**Feature:** {feature}")
    lines.append(f"**Problem:** {problem or '_(undefined)_'}")
    lines.append(f"**User:** {user or '_(undefined)_'}")
    lines.append(f"**Success metric:** {success_metric or '_(undefined)_'}")
    lines.append("")
    lines.append("## Technical constraints")
    lines.extend(_bullets(technical_constraints))
    lines.append("")
    lines.append("## Out of scope")
    lines.extend(_bullets(out_of_scope))
    lines.append("")
    lines.append("## Key risks / assumptions")
    lines.extend(_bullets(risks))
    if log_sections:
        lines.append("")
        lines.append("## Discover steps recorded")
        lines.extend(_bullets(log_sections))
    lines.append("")
    return "\n".join(lines)
