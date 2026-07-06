"""GitVCS (execution arc, T1-2) — the real merge.

Merges the feature branch into the repo's default branch with a real merge
commit (merge-commit-only enforced, as the simulator does), tags the release,
pushes, and returns the REAL sha + tag. A conflict or push failure raises so
the ship node fails visibly — a failed merge must never be reported as success
(that was the whole bug).
"""

from __future__ import annotations

import logging

from pdlc_graph.vcs_port import MergeStrategyError

from .workspace import RepoWorkspace, feature_branch

log = logging.getLogger("pdlc.runtime.vcs")


class GitMergeError(RuntimeError):
    """A real merge/push failed (conflict, non-fast-forward, auth, …)."""


class GitVCS:
    def merge_to_main(self, *, feature: str, version: str, description: str,
                      strategy: str = "merge") -> dict:
        if strategy != "merge":
            raise MergeStrategyError(
                f"refused merge strategy {strategy!r}: PDLC requires merge commits "
                f"(no squash, no rebase, no fast-forward)")

        from pdlc_graph.execution_context import current_execution_context

        ctx = current_execution_context()
        if ctx is None:
            raise GitMergeError("no execution context bound for the merge")
        branch = feature_branch(ctx.feature or feature, ctx.branch)
        ws = RepoWorkspace.acquire(ctx.project_id, branch=branch)
        default = ws.default_branch

        ws.git("checkout", "-B", default, f"origin/{default}")
        merge = ws.git("merge", "--no-ff", "-m", f"Merge {branch}: {description}",
                       branch, check=False)
        if merge.returncode != 0:
            ws.git("merge", "--abort", check=False)
            raise GitMergeError(
                f"merge of {branch} into {default} failed "
                f"(likely a conflict):\n{merge.stdout}\n{merge.stderr}"[:2000])

        sha = ws.git("rev-parse", "HEAD").stdout.strip()
        # Tag the release (idempotent-ish: -f so a re-run re-points the tag).
        ws.git("tag", "-f", version, check=False)
        push = ws.git("push", "origin", default, "--follow-tags", check=False)
        if push.returncode != 0:
            raise GitMergeError(
                f"push of {default} failed:\n{push.stdout}\n{push.stderr}"[:2000])
        log.info("merged %s -> %s (%s), tag %s", branch, default, sha[:10], version)
        return {"sha": sha[:40], "strategy": "merge", "version": version, "tag": version}


def wire_vcs(settings) -> bool:
    from .workspace import execution_enabled

    if not execution_enabled():
        return False
    from pdlc_graph.vcs_port import set_vcs

    set_vcs(GitVCS())
    log.info("real VCS wired (git merge/push)")
    return True
