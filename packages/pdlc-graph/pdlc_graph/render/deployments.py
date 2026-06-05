"""DEPLOYMENTS.md renderer — upstream templates/DEPLOYMENTS.md (01-ship.md Step 9.4).

Renders the deployment record Pulse writes after a successful merge + deploy:
an Environment block with a Tags table (carrying the safety-gating `tier`) and
a one-row Deployment History entry. Pure (kwargs -> str): no I/O.
"""

from __future__ import annotations


def render_deployments(
    *,
    feature: str,
    env: str,
    tier: str,
    version: str,
    url: str,
    sha: str,
    date: str,
) -> str:
    """Render a DEPLOYMENTS.md fragment for one deploy of `feature` to `env`."""
    lines: list[str] = []
    lines.append("# Deployments")
    lines.append("<!-- pdlc-template-version: 1.1.0 -->")
    lines.append("")
    lines.append("## Environments")
    lines.append("")
    lines.append(f"### Environment: {env}")
    lines.append("")
    lines.append(f"**Feature:** {feature}")
    lines.append(f"**URL:** {url}")
    lines.append("**Status:** active")
    lines.append("")
    lines.append("#### Tags")
    lines.append("")
    lines.append("| Key | Value | Notes |")
    lines.append("|-----|-------|-------|")
    lines.append(f"| tier | {tier} | Required for PDLC safety gating |")
    lines.append("")
    lines.append("#### Deployment History")
    lines.append("")
    lines.append("| Date | Version | Deployed by | SHA | Notes |")
    lines.append("|------|---------|-------------|-----|-------|")
    lines.append(f"| {date} | {version} | Pulse | {sha} | Deployed {feature} to {env} |")
    lines.append("")
    return "\n".join(lines)
