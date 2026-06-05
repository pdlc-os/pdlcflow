"""Hotfix record renderer — upstream skills/hotfix (compressed build->ship).

Renders the compact hotfix record Pulse writes after an emergency deploy:
the slug/summary, the shipped version, target environment, and confirmation
mode (human-confirmed vs night-shift auto). Pure (kwargs -> str): no I/O.
"""

from __future__ import annotations


def render_hotfix_record(
    *,
    summary: str,
    version: str,
    env: str,
    tier: str,
    date: str,
    auto: bool = False,
) -> str:
    """Render a compact hotfix record for one emergency deploy."""
    confirmation = "night-shift auto-proceed" if auto else "human-confirmed"
    lines: list[str] = []
    lines.append("# Hotfix Record")
    lines.append("")
    lines.append(f"**Date:** {date}")
    lines.append(f"**Summary:** {summary}")
    lines.append(f"**Version:** {version}")
    lines.append(f"**Environment:** {env}")
    lines.append(f"**Tier:** {tier}")
    lines.append(f"**Confirmation:** {confirmation}")
    lines.append("")
    lines.append(
        f"Emergency hotfix shipped to {env} as {version} ({confirmation}). "
        "TDD enforced; full Party Review skipped per hotfix protocol."
    )
    lines.append("")
    return "\n".join(lines)
