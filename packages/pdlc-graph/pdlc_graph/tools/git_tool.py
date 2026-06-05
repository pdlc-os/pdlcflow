"""git_* tools — clone, branch, commit, diff, log.

Phase A stubs. Real implementations land in Phase C with proper EFS access
points (SaaS) / local mounts (self-host) and per-tool guardrail wrappers.
"""

from langchain_core.tools import tool


@tool
def git_status(repository: str) -> str:
    """Return the porcelain status of the working tree."""
    return "stub: git status not yet wired"


@tool
def git_diff(repository: str, ref: str | None = None) -> str:
    """Return a unified diff against `ref` (default: HEAD)."""
    return "stub: git diff not yet wired"


@tool
def git_log(repository: str, n: int = 10) -> str:
    """Return the last `n` commit messages (oneline)."""
    return "stub: git log not yet wired"
