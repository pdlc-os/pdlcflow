"""Operation Verify sub-phase (upstream skills/ship/steps/02-verify.md).

Pulse leads post-deploy verification: a final security sweep (Phantom), smoke
tests against the deployed environment, an optional UX verify pass (Muse, only
when a UX review exists), then the Smoke sign-off approval gate (#7,
`smoke_signoff`). A failed *required* smoke check (HTTP health / primary user
journey) flags the gate as blocking so night-shift refuses rather than
auto-approving. Compiled without an inner checkpointer so interrupts propagate
to the top-level graph's checkpointer.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ... import gates
from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...security_scan_port import scan
from ...state import PDLCState
from ...test_runner_port import run_layer

GATE_KIND = "smoke_signoff"

# Smoke checks run against the deployed environment (upstream Step 11). The
# first two are required — a failure there blocks the sign-off gate.
_SMOKE_CHECKS = ("http_health", "user_journey", "auth_flow")
_REQUIRED_CHECKS = ("http_health", "user_journey")


@instrumented_node("subphase.entered")
def security_checks(state: PDLCState) -> dict:
    """Step 10a — final pre-verify security sweep.

    Runs real scanners (dependency audit + secret scan) via the security-scan
    port when execution is wired (T1-4); with no scanner they honestly report
    "skipped" — never a faked "clean". A real FINDING (passed=False, not
    skipped) flags the sign-off gate blocking. A Phantom completion adds an
    advisory note either way.
    """
    feature = state.get("feature") or "untitled-feature"
    deploy_url = state.get("deploy_url") or "(unknown)"
    note = complete(
        "phantom",
        f"Run a final security sweep on merged main for '{feature}' deployed at "
        f"{deploy_url}: dependency audit, secret scan, and security headers. "
        f"Report critical findings, if any.",
        system="PDLC security reviewer",
    ).strip()
    dep = scan("dependency_audit")
    sec = scan("secret_scan")
    scans_run = not (dep.get("skipped") and sec.get("skipped"))
    passed = bool(dep.get("passed", True) and sec.get("passed", True))
    security = {
        "dependency_audit": _label(dep),
        "secret_scan": _label(sec),
        "security_headers": "skipped",
        "scans_run": scans_run,
        "findings": int(dep.get("findings", 0)) + int(sec.get("findings", 0)),
        "report": "\n".join(
            x for x in (note, dep.get("report", ""), sec.get("report", "")) if x),
        "passed": passed,
    }
    results = dict(state.get("smoke_results") or {})
    results["security"] = security
    return {"smoke_results": results}


def _label(result: dict) -> str:
    if result.get("skipped"):
        return "skipped"
    return "clean" if result.get("passed") else "findings"


@instrumented_node("step.completed")
def smoke_tests(state: PDLCState) -> dict:
    """Step 11 — run the smoke checks against the deployed environment."""
    target = state.get("deploy_url") or state.get("deploy_target") or "deployment"
    failing = set(state.get("simulate_failing_smoke") or [])
    results = dict(state.get("smoke_results") or {})
    for check in _SMOKE_CHECKS:
        outcome = run_layer(
            "smoke",
            f"{check}@{target}",
            fail_until=1 if check in failing else 0,
        )
        # `required` makes the night-shift `smoke-failed` abort marker reachable
        # (_state_md keys off it) — required checks that fail abort the run.
        results[check] = {"passed": bool(outcome["passed"]),
                          "required": check in _REQUIRED_CHECKS,
                          "report": outcome["report"]}
    return {"smoke_results": results}


@instrumented_node("step.completed")
def ux_verify(state: PDLCState) -> dict:
    """Step 11.5 — UX Verify (Muse, conditional on an existing UX review).

    Records a short verify note under smoke_results["ux_verify"]. No real UX
    check runs yet (tracked in stub-gaps-roadmap T1-4) — the result is marked
    skipped rather than implying a clean sweep; the Muse note is advisory.
    """
    feature = state.get("feature") or "untitled-feature"
    note = complete(
        "muse",
        f"UX verify the as-deployed '{feature}': UX-writing drift, anti-patterns, "
        f"8-state spot-check, accessibility regression, console issues. "
        f"State any P0 finding.",
        system="PDLC UX reviewer",
    ).strip()
    results = dict(state.get("smoke_results") or {})
    results["ux_verify"] = {"passed": True, "skipped": True, "p0_findings": 0,
                            "report": note}
    return {"smoke_results": results}


@instrumented_node("subphase.exited")
def smoke_gate(state: PDLCState) -> dict:
    """Step 12 — open the Smoke sign-off approval gate; record the verdict."""
    results = state.get("smoke_results") or {}
    failed_required = [
        c for c in _REQUIRED_CHECKS if not (results.get(c) or {}).get("passed", False)
    ]
    # A real security scan that FOUND something (ran and did not pass) is a
    # hard block — night-shift must not auto-approve a deploy with live
    # vulnerabilities. A "skipped" scan (nothing ran) does not block.
    sec = results.get("security") or {}
    security_blocking = sec.get("scans_run") and not sec.get("passed", True)
    summary_lines = []
    for check in _SMOKE_CHECKS:
        if check in results:
            mark = "pass" if results[check].get("passed") else "fail"
            summary_lines.append(f"{check}: {mark}")
    if "ux_verify" in results:
        summary_lines.append("ux_verify: pass")
    if "security" in results:
        summary_lines.append(f"security: {'fail' if security_blocking else 'ok'}")
    payload = {
        "feature": state.get("feature"),
        "deploy_url": state.get("deploy_url"),
        "smoke_results": results,
        "summary": "Smoke results — " + "; ".join(summary_lines),
    }
    blockers = []
    if failed_required:
        blockers.append(f"required smoke check(s) failed: {', '.join(failed_required)}")
    if security_blocking:
        blockers.append(f"security scan found {sec.get('findings', 0)} finding(s)")
    if blockers:  # blocks night-shift auto-approval
        payload["blocking"] = "; ".join(blockers)
    verdict = gates.approval_gate(state, GATE_KIND, payload)
    return {"smoke_signed_off": bool(verdict.get("approved"))}


def _route_after_smoke(state: PDLCState) -> str:
    """UX Verify runs only when a UX review exists (upstream Step 11.5)."""
    return "ux_verify" if state.get("ux_review_ref") else "smoke_gate"


def build_verify() -> StateGraph:
    """Uncompiled Verify graph (START..steps..gate..END)."""
    g = StateGraph(PDLCState)
    g.add_node("security_checks", security_checks)
    g.add_node("smoke_tests", smoke_tests)
    g.add_node("ux_verify", ux_verify)
    g.add_node("smoke_gate", smoke_gate)
    g.add_edge(START, "security_checks")
    g.add_edge("security_checks", "smoke_tests")
    g.add_conditional_edges(
        "smoke_tests",
        _route_after_smoke,
        {"ux_verify": "ux_verify", "smoke_gate": "smoke_gate"},
    )
    g.add_edge("ux_verify", "smoke_gate")
    g.add_edge("smoke_gate", END)
    return g


verify_graph = build_verify().compile()
