"""gh_* tools — PR open, PR review, issue ops, check status.

All PR merges go through gh_pr_merge with strategy='merge' enforced —
upstream pdlc rule "merge commits, no squash, no rebase" survives the port.
Phase A stub.
"""

from langchain_core.tools import tool


@tool
def gh_pr_open(repository: str, title: str, body_ref: str) -> str:
    """Open a PR. `body_ref` is an S3 key for the PR body (no body content in tool args)."""
    return "stub: gh pr open not yet wired"


@tool
def gh_pr_merge(repository: str, number: int) -> str:
    """Merge a PR using the merge-commit strategy. Refuses squash/rebase."""
    return "stub: gh pr merge --merge not yet wired"
