"""Plan renderer — upstream skills/brainstorm/steps/04-plan.md (Step 17).

Assembles the Inception plan file from an already-created Beads task list:
a task table (bd id, title, labels, depends-on), the Mermaid dependency
graph, and a wave-based implementation order. Pure function: no I/O, no
model. The PLAN node builds the task list + mermaid, then calls this and
`ports.put_artifact(...)` to persist the returned string.
"""

from __future__ import annotations


def _labels(labels: list[str] | None) -> str:
    return ", ".join(f"`{lbl}`" for lbl in (labels or [])) or "_(none)_"


def _depends(depends_on: list[str] | None) -> str:
    return ", ".join(depends_on) if depends_on else "—"


def render_plan(
    *,
    feature: str,
    date: str,
    prd_ref: str | None = None,
    tasks: list[dict] | None = None,
    mermaid: str = "",
    waves: list[list[str]] | None = None,
) -> str:
    """Render the plan to markdown. Deterministic in its inputs.

    `tasks` is [{"external_id","title","labels","depends_on"}, ...]; `waves`
    is the execution order as a list of waves, each a list of external ids
    that can run in parallel.
    """
    tasks = tasks or []
    waves = waves or []
    by_id = {t.get("external_id"): t for t in tasks}

    L: list[str] = []
    L.append(f"# Plan: {feature}")
    L.append("")
    L.append(f"**Feature:** {feature}")
    L.append(f"**Date:** {date}")
    L.append(f"**PRD:** {prd_ref or '_(unlinked)_'}")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Tasks")
    L.append("")
    L.append("| Beads ID | Title | Labels | Depends On |")
    L.append("|----------|-------|--------|------------|")
    if not tasks:
        L.append("| _(none)_ | | | |")
    for t in tasks:
        L.append(
            f"| {t.get('external_id', '?')} | {t.get('title', '')} "
            f"| {_labels(t.get('labels'))} | {_depends(t.get('depends_on'))} |"
        )
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Dependency Graph")
    L.append("")
    L.append("```mermaid")
    L.append(mermaid.strip() or "graph TD")
    L.append("```")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## Implementation Order")
    L.append("")
    if not waves:
        L.append("_(no waves — no tasks)_")
    else:
        for n, wave in enumerate(waves, start=1):
            items = []
            for ext in wave:
                title = (by_id.get(ext) or {}).get("title", "")
                items.append(f"{ext} — {title}" if title else ext)
            joined = "; ".join(items)
            L.append(f"{n}. **Wave {n}** (parallel): {joined}")
    L.append("")

    return "\n".join(L)
