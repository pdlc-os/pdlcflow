"""SubprocessTestRunner (execution arc, T1-1) — the real test runner.

Runs the operator-configured command for each layer in the project's checked-out
workspace and reports the true exit code + output tail. Replaces the
SimulatedTestRunner's scripted pass/fail in the Construction/Operation loops
when execution is enabled (single-user self-host).

The simulator's `fail_until` (deterministic replay knob) is ignored — a real
suite genuinely passes or fails. Note: langgraph replays completed nodes on
resume, so a real run may re-execute; acceptable in the gated single-user
context and documented in the design doc.
"""

from __future__ import annotations

import logging
import subprocess

from ..config import settings
from .workspace import RepoWorkspace, feature_branch, run

log = logging.getLogger("pdlc.runtime.test")

_MAX_REPORT = 4000  # tail of captured output kept in the report


class SubprocessTestRunner:
    def run_layer(self, layer: str, target: str, *, attempt: int = 0,
                  fail_until: int = 0) -> dict:
        cmd = self._command_for(layer)
        try:
            ws = self._workspace()
            proc = run(["bash", "-lc", cmd], cwd=ws.path,
                       timeout=getattr(settings, "test_timeout_s", 600), check=False)
            passed = proc.returncode == 0
            report = _tail(proc)
        except subprocess.TimeoutExpired:
            passed, report = False, f"[{layer}] TIMEOUT after {settings.test_timeout_s}s"
        except Exception as exc:  # workspace/guard failure — surface, don't fake a pass
            passed, report = False, f"[{layer}] runner error: {type(exc).__name__}: {exc}"
        return {
            "passed": passed,
            "layer": layer,
            "target": target,
            "attempt": attempt,
            "report": f"[{layer}:{target}] {'PASS' if passed else 'FAIL'}\n{report}"[:_MAX_REPORT],
        }

    @staticmethod
    def _command_for(layer: str) -> str:
        return (getattr(settings, f"test_cmd_{layer}", None)
                or getattr(settings, "test_cmd", "true"))

    @staticmethod
    def _workspace() -> RepoWorkspace:
        from pdlc_graph.execution_context import current_execution_context

        ctx = current_execution_context()
        if ctx is None:
            raise RuntimeError("no execution context bound for this turn")
        return RepoWorkspace.acquire(
            ctx.project_id, branch=feature_branch(ctx.feature, ctx.branch))


def _tail(proc: subprocess.CompletedProcess) -> str:
    out = (proc.stdout or "") + (proc.stderr or "")
    return out[-_MAX_REPORT:] if len(out) > _MAX_REPORT else out


def wire_test_runner(settings) -> bool:
    """Inject the subprocess runner when execution is enabled (single-user
    self-host). Returns True if installed. Simulator stays otherwise."""
    from .workspace import execution_enabled

    if not execution_enabled():
        return False
    from pdlc_graph.test_runner_port import set_test_runner

    set_test_runner(SubprocessTestRunner())
    log.info("real test runner wired (subprocess execution)")
    return True
