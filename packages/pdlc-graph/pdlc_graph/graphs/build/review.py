"""Construction Review sub-phase (upstream skills/build/steps/03-review.md).

Party Review runs the always-on reviewers (Neo / Echo / Phantom / Jarvis, plus
Muse when a UX review exists), renders REVIEW.md, then opens the End-of-Review
approval gate (#5, `review_md_approve`). Critical findings flag the gate as
blocking so night-shift refuses rather than auto-approving.
"""

from __future__ import annotations

from datetime import date as _date

from ... import gates
from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...ports import put_artifact
from ...render import render_review
from ...state import PDLCState
from ..parties import run_party

GATE_KIND = "review_md_approve"

# Always-on reviewers + the dimension each owns (upstream Step 12).
_REVIEWERS = [
    ("neo", "Architecture", "Advisory"),
    ("echo", "Test coverage", "Advisory"),
    ("phantom", "Security", "Advisory"),
    ("jarvis", "Documentation", "Advisory"),
]


def _slug(feature: str) -> str:
    return feature.strip().lower().replace(" ", "-") or "feature"


@instrumented_node("subphase.entered")
def review_party(state: PDLCState) -> dict:
    """Step 12 — run Party Review, render REVIEW.md, persist it -> review_ref."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    today = _date.today().isoformat()

    roster = [r[0] for r in _REVIEWERS]
    if state.get("ux_review_ref"):
        roster.append("muse")

    party = run_party(
        feature=feature,
        project_id=project_id,
        kind="party-review",
        topic="Review the as-built feature across architecture, tests, security, docs",
        roster=roster,
        context="All tasks complete; cross-review the implementation.",
        night_shift_active=bool(state.get("night_shift_active")),
    )

    findings: list[dict] = []
    for reviewer, dimension, severity in _REVIEWERS:
        note = complete(
            reviewer,
            f"Review the as-built '{feature}' for {dimension}. State one finding.",
            system="PDLC reviewer",
        ).strip()
        findings.append(
            {
                "severity": severity,
                "reviewer": reviewer,
                "title": f"{dimension}: {note[:80]}",
                "reference": f"{_slug(feature)}/*",
                "action": "Address before ship" if severity == "Critical" else "Consider",
            }
        )

    review_md = render_review(
        feature=feature,
        date=today,
        reviewers=roster,
        findings=findings,
        mom_ref=party.get("mom_ref"),
    )
    path = f"docs/pdlc/reviews/REVIEW_{_slug(feature)}_{today}.md"
    review_ref = put_artifact(project_id, path, review_md)

    party_results = dict(state.get("party_results") or {})
    party_results["party-review"] = {**party, "critical": 0}
    return {"review_ref": review_ref, "party_results": party_results}


@instrumented_node("step.completed")
def review_gate(state: PDLCState) -> dict:
    """Step 13 — open the End-of-Review approval gate; record the verdict."""
    critical = (state.get("party_results") or {}).get("party-review", {}).get("critical", 0)
    payload = {
        "feature": state.get("feature"),
        "review_ref": state.get("review_ref"),
        "critical_findings": critical,
        "summary": "Review package ready; approve to proceed to Test.",
    }
    if critical:  # a Critical finding blocks night-shift auto-approval
        payload["blocking"] = f"{critical} critical review finding(s)"
    verdict = gates.approval_gate(state, GATE_KIND, payload)
    return {"review_approved": bool(verdict.get("approved"))}
