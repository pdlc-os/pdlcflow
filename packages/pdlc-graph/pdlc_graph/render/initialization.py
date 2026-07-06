"""Initialization renderers — CONSTITUTION / INTENT / ROADMAP (T3-2).

The three genesis artifacts a project is seeded with before Inception (upstream
skills/init/steps/*.md). Pure (kwargs -> str) transforms, no I/O — the init
sub-phase calls one, then `ports.put_artifact(...)`.
"""

from __future__ import annotations


def _bullets(items: list[str] | None, *, empty: str = "_none_") -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {it}" for it in items]


def render_constitution(
    *,
    project: str,
    date: str,
    principles: list[str] | None = None,
    tdd: bool = True,
    prod_deploy_ban: bool = True,
    interaction_mode: str = "socratic",
    notes: str | None = None,
) -> str:
    """The project's governing constitution — the non-negotiables a run honors."""
    lines: list[str] = []
    lines.append(f"# Constitution — {project}")
    lines.append("")
    lines.append(f"**Date:** {date}")
    lines.append("**Status:** ratified")
    lines.append("")
    lines.append("## Principles")
    lines.extend(_bullets(principles, empty="_(no additional principles)_"))
    lines.append("")
    lines.append("## Standing rules")
    lines.append(f"- TDD enforced: **{'yes' if tdd else 'no'}** "
                 "(no implementation without a failing test first)")
    lines.append(f"- Production-deploy ban: **{'yes' if prod_deploy_ban else 'no'}** "
                 "(production requires a human at the keyboard)")
    lines.append(f"- Default interaction mode: **{interaction_mode}**")
    lines.append("- Merge commits only (no squash, no rebase, no fast-forward)")
    if notes:
        lines.append("")
        lines.append("## Notes")
        lines.append(notes)
    lines.append("")
    return "\n".join(lines)


def render_intent(
    *,
    project: str,
    date: str,
    mission: str,
    target_users: str,
    success_metrics: list[str] | None = None,
    non_goals: list[str] | None = None,
) -> str:
    """The product intent — why this project exists and what winning looks like."""
    lines: list[str] = []
    lines.append(f"# Intent — {project}")
    lines.append("")
    lines.append(f"**Date:** {date}")
    lines.append("")
    lines.append(f"**Mission:** {mission or '_(undefined)_'}")
    lines.append(f"**Target users:** {target_users or '_(undefined)_'}")
    lines.append("")
    lines.append("## Success metrics")
    lines.extend(_bullets(success_metrics))
    lines.append("")
    lines.append("## Non-goals")
    lines.extend(_bullets(non_goals))
    lines.append("")
    return "\n".join(lines)


def render_roadmap(
    *,
    project: str,
    date: str,
    items: list[dict] | None = None,
) -> str:
    """The seed roadmap — the initial F-NNN feature list to draw Inception from.

    Each item: {"id"?, "title", "rationale"?}. Ids are assigned F-001.. when
    absent so downstream traceability (roadmap_id) has a handle from day one.
    """
    lines: list[str] = []
    lines.append(f"# Roadmap — {project}")
    lines.append("")
    lines.append(f"**Date:** {date}")
    lines.append("")
    lines.append("| ID | Feature | Rationale |")
    lines.append("|---|---|---|")
    rows = items or []
    if not rows:
        lines.append("| — | _(no seed features yet)_ | |")
    for i, item in enumerate(rows, start=1):
        fid = item.get("id") or f"F-{i:03d}"
        title = (item.get("title") or "").strip() or "_(untitled)_"
        rationale = (item.get("rationale") or "").strip() or "—"
        lines.append(f"| {fid} | {title} | {rationale} |")
    lines.append("")
    return "\n".join(lines)
