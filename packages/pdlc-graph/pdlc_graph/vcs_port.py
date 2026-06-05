"""VCS port — the merge seam, with merge-commit-only enforcement.

The upstream rule "merge commits, no squash, no rebase" (scripts/ship-merge.sh,
CONSTITUTION §6) is structural here: `merge_to_main` raises on any strategy
other than "merge". The default in-memory implementation simulates the merge
and returns a deterministic short SHA so the Operation loop runs hermetically;
the engine injects a real git/gh-backed implementation at boot.
"""

from __future__ import annotations

import hashlib
from typing import Protocol


class MergeStrategyError(Exception):
    """Raised when a non-merge-commit strategy is requested."""


class VCS(Protocol):
    def merge_to_main(self, *, feature: str, version: str, description: str, strategy: str = "merge") -> dict: ...


class SimulatedVCS:
    def merge_to_main(
        self, *, feature: str, version: str, description: str, strategy: str = "merge"
    ) -> dict:
        if strategy != "merge":
            raise MergeStrategyError(
                f"refused merge strategy {strategy!r}: PDLC requires merge commits "
                f"(no squash, no rebase, no fast-forward)"
            )
        sha = hashlib.sha256(f"{feature}|{version}|{description}".encode()).hexdigest()[:10]
        return {"sha": sha, "strategy": "merge", "version": version, "tag": version}


_vcs: VCS = SimulatedVCS()


def set_vcs(vcs: VCS) -> None:
    global _vcs
    _vcs = vcs


def reset_vcs() -> None:
    global _vcs
    _vcs = SimulatedVCS()


def merge_to_main(*, feature: str, version: str, description: str, strategy: str = "merge") -> dict:
    return _vcs.merge_to_main(feature=feature, version=version, description=description, strategy=strategy)
