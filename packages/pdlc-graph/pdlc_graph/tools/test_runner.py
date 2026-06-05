"""test_run tool — the persona-facing wrapper over the test-runner port.

Delegates to `pdlc_graph.test_runner_port` (the single source of truth the
Construction build loop also uses), so personas and the build loop never drift.
The default port is the deterministic offline simulator; the engine injects a
subprocess-backed runner at boot via `set_test_runner`.
"""

from langchain_core.tools import tool

from ..test_runner_port import run_layer


@tool
def test_run(repository: str, layer: str, target: str) -> str:
    """Run tests for `target` at `layer` (unit|integration|contract|e2e|security|perf|ux)."""
    result = run_layer(layer, target)
    status = "passed" if result["passed"] else "failed"
    return f"{layer}:{target} -> {status} ({result['report']})"
