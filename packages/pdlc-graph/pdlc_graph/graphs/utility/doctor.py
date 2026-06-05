"""/doctor utility node — bounded PDLC health check (read-only diagnostic).

Upstream: skills/doctor. A hermetic, bounded subset of the upstream checks: it
inspects the in-memory state (no git, no Beads, no filesystem scan) and reports
pass/fail per check. Builds a `doctor_report` dict, renders it to `doctor_ref`,
and summarizes pass/fail in `utility_result`.
"""

from __future__ import annotations

from ...instrumentation import instrumented_node
from ...ports import put_artifact
from ...render import render_doctor
from ...state import PDLCState


@instrumented_node("skill.invoked")
def doctor_node(state: PDLCState) -> dict:
    """Run the bounded health check and render the report."""
    blockers = state.get("active_blockers") or []
    blocker_count = len(blockers)

    checks = {
        "has_feature": bool(state.get("feature")),
        "has_phase": bool(state.get("phase")),
        "not_paused": not state.get("paused", False),
        "not_abandoned": not state.get("abandoned", False),
        "has_roadmap_claim": bool(state.get("roadmap_claim")),
        "no_blockers": blocker_count == 0,
    }
    details = {
        "has_phase": str(state.get("phase") or "—"),
        "no_blockers": f"{blocker_count} active blocker(s)",
    }
    passed = sum(1 for ok in checks.values() if ok)
    failed = len(checks) - passed

    report = {
        "feature": state.get("feature"),
        "phase": state.get("phase"),
        "checks": checks,
        "details": details,
        "blocker_count": blocker_count,
        "passed": passed,
        "failed": failed,
    }

    project_id = state.get("project_id") or "proj"
    doctor_md = render_doctor(report)
    doctor_ref = put_artifact(project_id, "docs/pdlc/doctor-report.md", doctor_md)

    return {
        "doctor_report": report,
        "doctor_ref": doctor_ref,
        "utility_result": {
            "command": "doctor",
            "passed": passed,
            "failed": failed,
            "healthy": failed == 0,
        },
    }
