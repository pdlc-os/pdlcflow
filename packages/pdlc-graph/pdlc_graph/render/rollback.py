"""Rollback note renderer — upstream skills/rollback (revert record).

Renders the compact rollback note Atlas writes when reverting a shipped
feature: the from -> to versions, the target environment, and a one-line
reason. Pure (kwargs -> str): no I/O.
"""

from __future__ import annotations


def render_rollback_note(
    *,
    feature: str,
    from_version: str,
    to_version: str,
    env: str,
    date: str,
    reason: str | None = None,
) -> str:
    """Render a rollback note for reverting `feature` to `to_version`."""
    lines: list[str] = []
    lines.append(f"# Rollback: {feature}")
    lines.append("")
    lines.append(f"**Date:** {date}")
    lines.append(f"**Environment:** {env}")
    lines.append(f"**Reverted from:** {from_version}")
    lines.append(f"**Rolled back to:** {to_version}")
    lines.append(f"**Reason:** {reason or 'not recorded'}")
    lines.append("")
    lines.append(
        f"Reverted {feature} from {from_version} to {to_version} on {env}. "
        "A post-mortem follows per the rollback protocol."
    )
    lines.append("")
    return "\n".join(lines)
