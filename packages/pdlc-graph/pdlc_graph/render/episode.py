"""Episode renderer — upstream templates/episode.md (Reflect Steps 13-14).

Renders the permanent episode record the episode_approve gate (#8) presents to
the human: what was built, links, key decisions, test summary, tradeoffs/tech
debt, the agent team, and Jarvis's Reflect Notes (what went well / what broke /
what to improve). Pure (kwargs -> str): no I/O, no model.
"""

from __future__ import annotations


def _bullets(items: list[str] | None, empty: str = "_None._") -> list[str]:
    items = [i for i in (items or []) if i]
    if not items:
        return [empty]
    return [f"- {i}" for i in items]


def _numbered(items: list[str] | None, empty: str = "_None._") -> list[str]:
    items = [i for i in (items or []) if i]
    if not items:
        return [empty]
    return [f"{n}. {i}" for n, i in enumerate(items, start=1)]


def render_episode(
    *,
    feature: str,
    episode_id: str,
    date: str,
    what_was_built: str,
    links: dict[str, str] | None = None,
    decisions: list[str] | None = None,
    test_summary: str = "",
    tradeoffs: list[str] | None = None,
    agent_team: list[str] | None = None,
    reflect_notes: dict | str | None = None,
) -> str:
    """Render the episode file to markdown. Deterministic in its inputs.

    `links` is {label: url}; `decisions`/`tradeoffs`/`agent_team` are lists of
    strings; `reflect_notes` is a dict with optional keys
    ``went_well`` / ``broke`` / ``improve`` (each a list[str]), or a plain
    string (used verbatim).
    """
    L: list[str] = []
    L.append(f"# Episode {episode_id}: {feature}")
    L.append("<!-- pdlc-template-version: 2.1.0 -->")
    L.append("")
    L.append(f"**Episode ID:** {episode_id}")
    L.append(f"**Feature name:** {feature}")
    L.append(f"**Date delivered:** {date}")
    L.append("**Phase delivered in:** Operation")
    L.append("**Status:** Draft")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## What Was Built")
    L.append("")
    L.append(what_was_built.strip() or "_To be written._")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Links")
    L.append("")
    links = links or {}
    if links:
        L.extend(f"- **{label}:** {url}" for label, url in links.items())
    else:
        L.append("_No links recorded._")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Key Decisions & Rationale")
    L.append("")
    L.extend(_numbered(decisions))
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Test Summary")
    L.append("")
    L.append(test_summary.strip() or "_No test summary recorded._")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Known Tradeoffs & Tech Debt Introduced")
    L.append("")
    L.extend(_bullets(tradeoffs, empty="_None._"))
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Agent Team")
    L.append("")
    L.extend(_bullets(agent_team, empty="_Not recorded._"))
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Reflect Notes")
    L.append("")
    if isinstance(reflect_notes, str):
        L.append(reflect_notes.strip() or "_None._")
    else:
        notes = reflect_notes or {}
        L.append("**What went well:**")
        L.extend(_bullets(notes.get("went_well")))
        L.append("")
        L.append("**What broke or slowed us down:**")
        L.extend(_bullets(notes.get("broke")))
        L.append("")
        L.append("**What to improve next time:**")
        L.extend(_bullets(notes.get("improve")))
    L.append("")
    return "\n".join(L)
