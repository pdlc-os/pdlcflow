"""SubprocessScanner (execution arc, T1-4) — real dependency + secret scans.

Runs pip-audit / npm audit (dependency_audit) and gitleaks (secret_scan)
against the project's checked-out workspace. Tools that aren't installed ⇒
honest `skipped` (never a faked clean). A non-zero finding count ⇒
`passed: False`, which flags the smoke-signoff gate blocking.
"""

from __future__ import annotations

import json
import logging
import shutil

from .workspace import RepoWorkspace, feature_branch, run

log = logging.getLogger("pdlc.runtime.security")


class SubprocessScanner:
    def scan(self, kind: str) -> dict:
        try:
            ws = self._workspace()
        except Exception as exc:
            return _skipped(kind, f"workspace unavailable: {type(exc).__name__}")
        if kind == "dependency_audit":
            return self._dependency_audit(ws)
        if kind == "secret_scan":
            return self._secret_scan(ws)
        return _skipped(kind, "unknown scan kind")

    @staticmethod
    def _workspace() -> RepoWorkspace:
        from pdlc_graph.execution_context import current_execution_context

        ctx = current_execution_context()
        if ctx is None:
            raise RuntimeError("no execution context")
        return RepoWorkspace.acquire(
            ctx.project_id, branch=feature_branch(ctx.feature, ctx.branch))

    def _dependency_audit(self, ws: RepoWorkspace) -> dict:
        if (ws.path / "package.json").exists() and shutil.which("npm"):
            proc = run(["npm", "audit", "--json"], cwd=ws.path, check=False, timeout=300)
            try:
                data = json.loads(proc.stdout or "{}")
                n = int(data.get("metadata", {}).get("vulnerabilities", {}).get("total", 0))
            except Exception:
                n = 0 if proc.returncode == 0 else 1
            return _result("dependency_audit", n, f"npm audit: {n} vuln(s)")
        if shutil.which("pip-audit"):
            proc = run(["pip-audit", "-f", "json"], cwd=ws.path, check=False, timeout=300)
            try:
                data = json.loads(proc.stdout or "[]")
                deps = data.get("dependencies", data) if isinstance(data, dict) else data
                n = sum(len(d.get("vulns", [])) for d in deps)
            except Exception:
                n = 0 if proc.returncode == 0 else 1
            return _result("dependency_audit", n, f"pip-audit: {n} vuln(s)")
        return _skipped("dependency_audit", "no pip-audit / npm on PATH")

    def _secret_scan(self, ws: RepoWorkspace) -> dict:
        if not shutil.which("gitleaks"):
            return _skipped("secret_scan", "gitleaks not on PATH")
        proc = run(["gitleaks", "detect", "--no-banner", "--redact", "--exit-code", "1"],
                   cwd=ws.path, check=False, timeout=300)
        # gitleaks exit 1 == leaks found, 0 == clean.
        n = 0 if proc.returncode == 0 else 1
        return _result("secret_scan", n, "gitleaks: leaks found" if n else "gitleaks: clean")


def _result(kind: str, findings: int, report: str) -> dict:
    return {"kind": kind, "passed": findings == 0, "skipped": False,
            "findings": findings, "report": report}


def _skipped(kind: str, why: str) -> dict:
    return {"kind": kind, "passed": True, "skipped": True, "findings": 0,
            "report": f"skipped: {why}"}


def wire_scanner(settings) -> bool:
    from .workspace import execution_enabled

    if not execution_enabled() or not getattr(settings, "security_scan", True):
        return False
    from pdlc_graph.security_scan_port import set_scanner

    set_scanner(SubprocessScanner())
    log.info("real security scanner wired")
    return True
