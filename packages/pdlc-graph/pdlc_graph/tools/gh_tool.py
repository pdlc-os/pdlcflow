"""gh_* tools — PR open, PR merge.

All PR merges go through the VCS port with strategy='merge' enforced — the
upstream rule "merge commits, no squash, no rebase" survives the port. PR open
remains a thin stub until the GitHub App is wired (Phase H).
"""

from langchain_core.tools import tool

from ..vcs_port import MergeStrategyError, merge_to_main


@tool
def gh_pr_open(repository: str, title: str, body_ref: str) -> str:
    """Open a PR. `body_ref` is an S3 key for the PR body (no body content in tool args)."""
    return f"stub: gh pr open ({title}) — GitHub App wiring lands in Phase H"


@tool
def gh_pr_merge(repository: str, feature: str, version: str, description: str = "") -> str:
    """Merge to main via the merge-commit strategy (refuses squash/rebase)."""
    try:
        result = merge_to_main(feature=feature, version=version, description=description)
    except MergeStrategyError as exc:
        return f"refused: {exc}"
    return f"merged {feature} as {result['tag']} (sha {result['sha']}, --no-ff)"
