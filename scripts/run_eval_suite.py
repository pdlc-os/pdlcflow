#!/usr/bin/env python
"""Run the eval golden suite and emit a JSON report — with optional drift check.

Modes:
  (hermetic, default)  uv run python scripts/run_eval_suite.py
      Enables the harness with the deterministic stub judge, scores every suite
      case, and (if a baseline exists) fails on any score regression. This is the
      nightly's drift guard for deterministic evals + harness wiring.

  (real LLM)           uv run python scripts/run_eval_suite.py --real
      Wires the factory-backed LLM-as-judge (needs PDLC_WIRE_LLM + provider creds)
      so the scores reflect actual model judgements. Report-only by default.

  (baseline)           uv run python scripts/run_eval_suite.py --write-baseline
      Regenerate suite_baseline.json from the current (stub) scores.

The report is printed to stdout and written to --out if given. With
--fail-on-regress TOL, exits non-zero if any (case::eval) score drops more than
TOL below the baseline.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from pdlc_graph.evals import set_evals_enabled
from pdlc_graph.evals.suite import (
    check_drift,
    default_baseline_path,
    default_suite_path,
    score_suite,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the pdlcflow eval golden suite.")
    ap.add_argument("--suite", default=str(default_suite_path()))
    ap.add_argument("--baseline", default=str(default_baseline_path()))
    ap.add_argument("--out", default=None, help="write the JSON report here")
    ap.add_argument("--real", action="store_true", help="wire the factory-backed judge (needs creds)")
    ap.add_argument("--write-baseline", action="store_true", help="(re)generate the baseline from current scores")
    ap.add_argument("--fail-on-regress", type=float, default=None, metavar="TOL",
                    help="exit 1 if any score drops > TOL below the baseline")
    args = ap.parse_args()

    set_evals_enabled(True)
    if args.real:
        # Wire the real LLM-as-judge via the engine (judge resolves through the factory).
        from app.config import settings
        from app.evals import wire_evals
        settings.run_evals = True
        settings.wire_llm = True
        wire_evals(settings)

    rows, flat = score_suite(pathlib.Path(args.suite))

    if args.write_baseline:
        pathlib.Path(args.baseline).write_text(json.dumps(flat, indent=2, sort_keys=True) + "\n")
        print(f"wrote baseline: {args.baseline} ({len(flat)} scores)")
        return 0

    tol = args.fail_on_regress if args.fail_on_regress is not None else 0.0
    regressions = check_drift(flat, pathlib.Path(args.baseline), tol=tol)

    report = {"mode": "real" if args.real else "stub", "scores": flat,
              "results": rows, "regressions": regressions}
    out = json.dumps(report, indent=2)
    if args.out:
        pathlib.Path(args.out).write_text(out + "\n")
    print(out)

    if args.fail_on_regress is not None and regressions:
        print(f"\nFAIL: {len(regressions)} regression(s) vs baseline", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
