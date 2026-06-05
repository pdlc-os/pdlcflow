"""Test-runner port — the graph's seam to the real test suite.

The Construction loop never shells out directly; it calls `run_layer(...)` here.
The default `SimulatedTestRunner` is deterministic and offline so the whole
build loop (TDD red→green→refactor, 3-Strike escalation, the 7 test layers)
runs in CI with no project checkout. The engine injects a subprocess-backed
runner at boot via `set_test_runner`.

Determinism contract (load-bearing — the build_loop node replays on every
resume): `run_layer` must be a pure function of its arguments. The simulated
runner fails the first `fail_until` attempts of a target, then passes; this is
how a task with `simulate_failures: 3` deterministically trips the Strike Panel.
"""

from __future__ import annotations

from typing import Protocol


class TDDViolation(Exception):
    """Raised when implementation is attempted before a failing test exists.

    This is the structural form of the upstream rule: "No implementation code
    without a failing test first. This is non-negotiable." (skills/tdd/SKILL.md)
    """


def assert_red_before_green(has_failing_test: bool, task_id: str) -> None:
    """Guard the green phase. Call before writing any implementation."""
    if not has_failing_test:
        raise TDDViolation(
            f"task {task_id}: cannot implement before a failing test is recorded "
            f"(red phase). Write the test first."
        )


class RunnerPort(Protocol):
    def run_layer(self, layer: str, target: str, *, attempt: int = 0, fail_until: int = 0) -> dict: ...


class SimulatedTestRunner:
    """Deterministic, offline stand-in for a real test runner."""

    def run_layer(self, layer: str, target: str, *, attempt: int = 0, fail_until: int = 0) -> dict:
        passed = attempt >= fail_until
        status = "passed" if passed else "failed"
        return {
            "passed": passed,
            "layer": layer,
            "target": target,
            "attempt": attempt,
            "report": f"[sim] {layer}:{target} attempt {attempt} -> {status}",
        }


_runner: RunnerPort = SimulatedTestRunner()


def set_test_runner(runner: RunnerPort) -> None:
    global _runner
    _runner = runner


def reset_test_runner() -> None:
    global _runner
    _runner = SimulatedTestRunner()


def run_layer(layer: str, target: str, *, attempt: int = 0, fail_until: int = 0) -> dict:
    return _runner.run_layer(layer, target, attempt=attempt, fail_until=fail_until)
