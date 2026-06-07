"""Sentinel evaluator — verbatim port of upstream hooks/pdlc-night-shift.js.

Reads `ns-progress:` and `ns-abort:` markers out of the run's state document
and returns a JSON-shaped verdict the runtime relays without paraphrase.

Verdict shape:
  {"ok": True,  "verdict": "continue"}        — loop continues
  {"ok": True,  "verdict": "complete"}        — loop exits cleanly
  {"ok": False, "verdict": "abort", "reason": "<condition-id>"}
"""

from __future__ import annotations

import re
from typing import TypedDict


class Verdict(TypedDict, total=False):
    ok: bool
    verdict: str
    reason: str


# Verbatim from upstream hooks/pdlc-night-shift.js — adding to this set is a
# breaking change to the night-shift contract; coordinate with /night-shift
# documentation and the Nexus Console mission-control filter.
ABORT_CONDITIONS: set[str] = {
    "critical-security",
    "p0-ux",
    "semver-ambiguous",
    "merge-conflict",
    "smoke-failed",
    "prod-deploy-attempted",
    "wrong-env-deploy",
    "env-untagged",
    "review-fix-cycles-3",
    "build-loop-iteration-cap",
    "stagnation",
    "deploy-url-unknown",
}

_PROGRESS_RE = re.compile(r"ns-progress:([a-z0-9-]+)")
_ABORT_RE = re.compile(r"ns-abort:([a-z0-9-]+)")


def evaluate(run_state: dict, state_md: str) -> Verdict:
    """Mechanical evaluator. Reads the run's state markers, returns a verdict.

    `run_state` is the active-run state document (the equivalent of upstream's
    `pdlc-night-shift.json`). `state_md` is the current STATE.md contents
    (the Guardrail Log section is the source of truth for `ns-*` markers).
    """
    aborts = _ABORT_RE.findall(state_md)
    for a in aborts:
        if a in ABORT_CONDITIONS:
            return {"ok": False, "verdict": "abort", "reason": a}

    progress = _PROGRESS_RE.findall(state_md)
    if "complete" in progress:
        return {"ok": True, "verdict": "complete"}

    if _stalled(run_state, progress):
        return {"ok": False, "verdict": "abort", "reason": "stagnation"}

    return {"ok": True, "verdict": "continue"}


def _stalled(run_state: dict, progress: list[str]) -> bool:
    """Stagnation: no new progress marker since last fire AND no abort marker.

    The real implementation compares fire counts. Phase A stub: always False
    (no false aborts during scaffold smoke runs).
    """
    return False
