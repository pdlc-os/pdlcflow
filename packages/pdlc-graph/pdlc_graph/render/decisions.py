"""DECISIONS.md renderer — upstream skills/decide (Decision Registry).

Renders the append-only Decision Registry as a markdown table, one row per
recorded ADR-style decision. Pure (list -> str): no I/O.
"""

from __future__ import annotations


def _cell(value: str | None) -> str:
    """Sanitize a value for a markdown table cell (no raw pipes/newlines)."""
    text = str(value if value is not None else "—").strip()
    return text.replace("|", "\\|").replace("\n", " ") or "—"


def render_decisions(decisions: list[dict]) -> str:
    """Render the Decision Registry as a DECISIONS.md table.

    Each decision dict may carry: id, title, rationale, date.
    """
    lines: list[str] = ["# Decisions", ""]
    if not decisions:
        lines.append("_No decisions recorded._")
        return "\n".join(lines).rstrip() + "\n"

    lines.append("| ID | Title | Rationale | Date |")
    lines.append("|----|-------|-----------|------|")
    for d in decisions:
        lines.append(
            f"| {_cell(d.get('id'))} | {_cell(d.get('title'))} "
            f"| {_cell(d.get('rationale'))} | {_cell(d.get('date'))} |"
        )
    return "\n".join(lines).rstrip() + "\n"
