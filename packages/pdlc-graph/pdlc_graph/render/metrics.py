"""Metrics renderer — upstream templates/METRICS.md (Reflect Step 16g).

Renders the per-episode Delivery Metrics row plus a one-line trend the Reflect
sub-phase appends to METRICS.md after every ship. Pure (kwargs -> str): no I/O.
"""

from __future__ import annotations


def render_metrics(
    *,
    feature: str,
    episode_id: str,
    date: str,
    cycle_days: int,
    test_pass_pct: float,
    review_rounds: int,
    strikes: int,
    tasks: int,
) -> str:
    """Render a single-episode metrics rollup to markdown.

    Emits the Delivery Metrics header + the one row for this episode, followed
    by a one-line trend summarising the headline numbers. Deterministic.
    """
    pct = f"{test_pass_pct:g}%"
    L: list[str] = []
    L.append(f"# Metrics — {feature}")
    L.append("<!-- pdlc-template-version: 2.3.0 -->")
    L.append("")
    L.append(f"**Episode:** {episode_id}")
    L.append(f"**Last updated:** {date}")
    L.append("")
    L.append("## Delivery Metrics")
    L.append("")
    L.append(
        "| Episode | Feature | Type | Cycle Days | Test Pass % | "
        "Review Rounds | Strikes | Tasks | Date Shipped |"
    )
    L.append("|---------|---------|------|-----------|-------------|---------------|---------|-------|-------------|")
    L.append(
        f"| {episode_id} | {feature} | Feature | {cycle_days} | {pct} | "
        f"{review_rounds} | {strikes} | {tasks} | {date} |"
    )
    L.append("")
    L.append("## Trend")
    L.append("")
    L.append(
        f"Episode {episode_id} shipped in {cycle_days} day(s) at {pct} test pass "
        f"across {tasks} task(s), {review_rounds} review round(s) and {strikes} strike(s)."
    )
    L.append("")
    return "\n".join(L)
