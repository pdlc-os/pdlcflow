"""REVIEW.md renderer — upstream templates/review.md (Construction Step 12).

Renders the Party Review artifact the End-of-Review gate (#5) presents to the
human: findings from the always-on reviewers (Neo / Echo / Phantom / Jarvis,
plus Muse when a UX review exists), each tagged Critical / Important / Advisory.
Pure (kwargs -> str): no I/O.
"""

from __future__ import annotations

_SEVERITY_ORDER = {"Critical": 0, "Important": 1, "Advisory": 2}


def render_review(
    *,
    feature: str,
    date: str,
    reviewers: list[str],
    findings: list[dict],
    mom_ref: str | None = None,
) -> str:
    """Render REVIEW.md. `findings` is
    [{"severity","reviewer","title","reference","action"}, ...]."""
    ordered = sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "Advisory"), 3))
    critical = [f for f in ordered if f.get("severity") == "Critical"]

    lines: list[str] = []
    lines.append(f"# Review — {feature}")
    lines.append("<!-- pdlc-template-version: 1.0.0 -->")
    lines.append("")
    lines.append(f"**Date:** {date}")
    lines.append(f"**Reviewers:** {', '.join(reviewers)}")
    lines.append(f"**Findings:** {len(ordered)} ({len(critical)} Critical)")
    if mom_ref:
        lines.append(f"**MOM:** {mom_ref}")
    lines.append("")
    lines.append("## Findings")
    if ordered:
        lines.append("| # | Severity | Reviewer | Finding | Reference | Recommended action |")
        lines.append("|---|---|---|---|---|---|")
        for i, f in enumerate(ordered, start=1):
            lines.append(
                f"| {i} | {f.get('severity', 'Advisory')} | {f.get('reviewer', '?')} | "
                f"{f.get('title', '')} | {f.get('reference', '')} | {f.get('action', '')} |"
            )
    else:
        lines.append("_No findings — clean review._")
    lines.append("")
    lines.append("## Gate")
    if critical:
        lines.append(
            f"{len(critical)} Critical finding(s) must be fixed or explicitly overridden "
            f"before this feature can ship."
        )
    else:
        lines.append("No Critical findings. Approve / Fix / Accept-warning / Defer.")
    lines.append("")
    return "\n".join(lines)
