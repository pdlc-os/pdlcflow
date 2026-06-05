"""CHANGELOG renderer — upstream 01-ship.md Step 5 (Conventional Changelog).

Renders one release entry the Ship gate (#6) shows the human before merge:
a versioned heading plus Added / Changed / Fixed / Breaking Changes sections.
Pure (kwargs -> str): no I/O.
"""

from __future__ import annotations


def _section(heading: str, bullets: list[str]) -> list[str]:
    if not bullets:
        return []
    out = [f"### {heading}", ""]
    out.extend(f"- {b}" for b in bullets)
    out.append("")
    return out


def render_changelog(
    *,
    version: str,
    date: str,
    added: list[str] | None = None,
    changed: list[str] | None = None,
    fixed: list[str] | None = None,
    breaking: list[str] | None = None,
) -> str:
    """Render a single CHANGELOG entry in Conventional Changelog format."""
    lines: list[str] = [f"## {version} — {date}", ""]
    body: list[str] = []
    body += _section("Added", added or [])
    body += _section("Changed", changed or [])
    body += _section("Fixed", fixed or [])
    body += _section("Breaking Changes", breaking or [])
    if body:
        lines += body
    else:
        lines += ["_No changes recorded._", ""]
    return "\n".join(lines).rstrip() + "\n"
