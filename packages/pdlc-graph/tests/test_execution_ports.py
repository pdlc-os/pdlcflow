"""Execution-arc port seams (graph side): deploy(), security scan, sentinel
stagnation, and verify's security-blocking. No subprocess/network here — the
engine-side tests exercise the real backends."""

from __future__ import annotations

import pytest
from pdlc_graph.deploy_port import deploy, reset_deployer, set_deployer
from pdlc_graph.security_scan_port import reset_scanner, scan, set_scanner
from pdlc_graph.sentinel.evaluator import _stalled, evaluate


@pytest.fixture(autouse=True)
def _clean():
    reset_deployer()
    reset_scanner()
    yield
    reset_deployer()
    reset_scanner()


# ----- deploy seam -------------------------------------------------------------


def test_deploy_default_is_honest_simulation():
    out = deploy(env="staging", ref="abc", feature="dark mode")
    assert out == {"url": None, "id": None, "simulated": True}


def test_deploy_injected_backend_wins():
    class _Fake:
        def deploy(self, *, env, ref, feature):
            return {"url": f"https://{env}.real.app", "id": ref, "simulated": False}

    set_deployer(_Fake())
    out = deploy(env="staging", ref="sha1", feature="f")
    assert out["url"] == "https://staging.real.app" and out["simulated"] is False


# ----- security scan port ------------------------------------------------------


def test_scan_default_is_skipped_not_clean():
    out = scan("dependency_audit")
    assert out["skipped"] is True and out["passed"] is True and out["findings"] == 0


def test_scan_injected_and_error_safe():
    class _Fake:
        def scan(self, kind):
            if kind == "secret_scan":
                raise RuntimeError("gitleaks blew up")
            return {"kind": kind, "passed": False, "skipped": False,
                    "findings": 2, "report": "2 vulns"}

    set_scanner(_Fake())
    dep = scan("dependency_audit")
    assert dep["findings"] == 2 and dep["passed"] is False and dep["skipped"] is False
    # a scanner exception degrades to skipped, never a false clean/finding
    sec = scan("secret_scan")
    assert sec["skipped"] is True


# ----- sentinel stagnation (T2-3) ----------------------------------------------


def test_stalled_only_fires_after_repeated_stagnation():
    assert _stalled({}, []) is False                              # no log
    assert _stalled({"night_shift_progress_log": ["a", "b"]}, []) is False  # progressing
    # 3 identical fingerprints (limit+1) → stalled
    assert _stalled({"night_shift_progress_log": ["a", "a", "a"]}, []) is True
    # forward progress in the tail → not stalled
    assert _stalled({"night_shift_progress_log": ["a", "a", "b"]}, []) is False


def test_evaluate_stagnation_verdict():
    v = evaluate({"night_shift_progress_log": ["x", "x", "x"]}, "")
    assert v == {"ok": False, "verdict": "abort", "reason": "stagnation"}
    # happy path (distinct fingerprints) continues
    v2 = evaluate({"night_shift_progress_log": ["build-done", "build-done|complete"]}, "")
    assert v2["verdict"] == "continue"


# ----- verify security-blocking ------------------------------------------------


def test_verify_security_finding_blocks_gate():
    from pdlc_graph.graphs.ship.verify import security_checks, smoke_gate
    from pdlc_graph.llm_port import reset_completion_backend

    reset_completion_backend()  # stub completion for the Phantom note

    class _Findings:
        def scan(self, kind):
            return {"kind": kind, "passed": False, "skipped": False,
                    "findings": 3, "report": f"{kind}: 3 issues"}

    set_scanner(_Findings())
    state = {"feature": "f", "deploy_url": "https://x", "smoke_results": {
        "http_health": {"passed": True, "required": True},
        "user_journey": {"passed": True, "required": True},
    }}
    state.update(security_checks(state))
    sec = state["smoke_results"]["security"]
    assert sec["scans_run"] is True and sec["passed"] is False and sec["findings"] == 6
    # the gate payload must carry a blocking reason (night-shift refuses)
    from pdlc_graph import gates

    captured = {}

    def _spy_gate(st, kind, payload):
        captured.update(payload)
        return {"approved": True}

    orig = gates.approval_gate
    gates.approval_gate = _spy_gate
    try:
        smoke_gate(state)
    finally:
        gates.approval_gate = orig
    assert "blocking" in captured and "security scan found" in captured["blocking"]
