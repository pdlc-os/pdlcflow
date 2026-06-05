"""MOM (Minutes of Meeting) renderer — upstream docs/pdlc/mom/ shape.

Produces the markdown a party meeting (Progressive Thinking, Threat-Model,
Design-Laws) leaves behind. Pure function: no I/O.
"""

from __future__ import annotations


def render_mom(
    *,
    feature: str,
    topic: str,
    mode: str,
    participants: list[str],
    context: str,
    pitches: list[dict],
    decision: str,
    next_steps: list[str] | None = None,
) -> str:
    """Render a MOM. `pitches` is [{"persona": str, "pitch": str}, ...]."""
    lines: list[str] = []
    lines.append("---")
    lines.append(f"feature: {feature}")
    lines.append(f"topic: {topic}")
    lines.append(f"mode: {mode}")
    lines.append(f"participants: {', '.join(participants)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# MOM — {topic} — {feature}")
    lines.append("")
    lines.append("## Context")
    lines.append(context or "_(none provided)_")
    lines.append("")
    lines.append("## Discussion")
    if pitches:
        for p in pitches:
            lines.append(f"### {p.get('persona', '?')}")
            lines.append(p.get("pitch", "").strip() or "_(no pitch)_")
            lines.append("")
    else:
        lines.append("_No pitches recorded._")
        lines.append("")
    lines.append("## Decision")
    lines.append(decision or "_deferred_")
    lines.append("")
    lines.append("## Next steps")
    if next_steps:
        for s in next_steps:
            lines.append(f"- {s}")
    else:
        lines.append("- _none_")
    lines.append("")
    return "\n".join(lines)
