"""Doctor report renderer — upstream skills/doctor (health check).

Renders the bounded, hermetic doctor health-check report: a summary line plus a
checks table (name / status / detail). Pure (dict -> str): no I/O.
"""

from __future__ import annotations


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def render_doctor(report: dict) -> str:
    """Render a doctor_report dict to a DOCTOR.md report."""
    checks: dict = report.get("checks") or {}
    passed = report.get("passed", sum(1 for v in checks.values() if v))
    failed = report.get("failed", sum(1 for v in checks.values() if not v))

    lines: list[str] = ["# Doctor Report", ""]
    lines.append(f"**Feature:** {report.get('feature') or '—'}")
    lines.append(f"**Phase:** {report.get('phase') or '—'}")
    lines.append(f"**Summary:** {passed} passed, {failed} failed")
    lines.append("")
    lines.append("| Check | Status | Detail |")
    lines.append("|-------|--------|--------|")
    for name, ok in checks.items():
        detail = (report.get("details") or {}).get(name, "")
        lines.append(f"| {name} | {_status(bool(ok))} | {detail} |")
    return "\n".join(lines).rstrip() + "\n"
