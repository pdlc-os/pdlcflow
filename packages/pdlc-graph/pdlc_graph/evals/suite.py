"""Golden-suite scoring + drift comparison (used by the CLI + the eval tests).

`score_suite` runs every case in the suite through the evals registered for its
trigger and returns flat `{case::eval_id: score}`. `check_drift` compares those
scores to a committed baseline and reports regressions (scores that dropped more
than a tolerance). Deterministic under the stub judge — so a code change that
shifts a score is caught as drift; under the real judge it tracks model quality.
"""

from __future__ import annotations

import json
import pathlib

from .runner import run_evals_for
from .schema import EvalContext

_GOLDEN = pathlib.Path(__file__).parent / "golden"


def default_suite_path() -> pathlib.Path:
    return _GOLDEN / "suite.json"


def default_baseline_path() -> pathlib.Path:
    return _GOLDEN / "suite_baseline.json"


def score_suite(suite_path: pathlib.Path | None = None) -> tuple[list[dict], dict[str, float]]:
    cases = json.loads((suite_path or default_suite_path()).read_text())["cases"]
    rows: list[dict] = []
    flat: dict[str, float] = {}
    for c in cases:
        results = run_evals_for(EvalContext(
            trigger=c["trigger"], target=c["target"], output=c.get("output", ""),
            sources=c.get("sources", {}), extra=c.get("extra", {}),
        ))
        for r in results:
            rows.append({"case": c["id"], **r.to_payload()})
            flat[f"{c['id']}::{r.eval_id}"] = round(float(r.score), 4)
    return rows, flat


def check_drift(flat: dict[str, float], baseline_path: pathlib.Path | None = None,
                tol: float = 0.0) -> list[dict]:
    base_path = baseline_path or default_baseline_path()
    if not base_path.exists():
        return []
    base = json.loads(base_path.read_text())
    regressions: list[dict] = []
    for key, base_score in base.items():
        cur = flat.get(key)
        if cur is None:
            regressions.append({"key": key, "kind": "missing", "baseline": base_score, "current": None})
        elif cur < base_score - tol:
            regressions.append({"key": key, "kind": "regress", "baseline": base_score, "current": cur})
    return regressions
