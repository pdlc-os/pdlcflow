"""Construction build loop (upstream skills/build/steps/02-build-loop.md + tdd).

One deterministic node walks the waves and, per task, runs the TDD micro-loop:

    red    — write the failing test first (records `has_failing_test`)
    green  — minimal implementation; run the unit layer; auto-fix up to 3 times
    3-Strike — on the 3rd failed attempt convene the Strike Panel (Neo + Echo +
               domain agent), surface 3 ranked approaches, and pause for the
               human to pick (interrupt). The counter resets after the choice.
    refactor — clean up; full unit layer must stay green.

Per-wave it optionally runs a Wave Kickoff standup; per-task it optionally runs
a Design Roundtable (both via the generic party orchestrator, triage-gated).

This is a single node with (possibly many) interrupt() sites — the same
replay-safe pattern as Discover's Socratic loop. All work is deterministic on
replay: the LLM and test-runner ports are pure, party invocations recompute,
and the only mutations are returned as a state patch.
"""

from __future__ import annotations

from langgraph.types import interrupt

from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...state import PDLCState
from ...test_runner_port import assert_red_before_green, run_layer
from ..parties import run_party
from .preflight import compute_waves

_MAX_ATTEMPTS = 6  # hard safety cap (3-Strike resolves well before this)

_DOMAIN_AGENT = {
    "backend": "bolt",
    "frontend": "friday",
    "devops": "pulse",
    "ux": "muse",
    "product": "atlas",
}


def _domain_of(task: dict) -> str:
    for label in task.get("labels") or []:
        if label.startswith("domain:"):
            return label.split(":", 1)[1]
    return ""


def _domain_agent(task: dict) -> str:
    return _DOMAIN_AGENT.get(_domain_of(task), "bolt")


def _needs_roundtable(task: dict) -> bool:
    """Design Roundtable auto-trigger (subset of upstream signals)."""
    domains = {label.split(":", 1)[1] for label in (task.get("labels") or []) if label.startswith("domain:")}
    return len(domains) > 1 or bool(task.get("needs_design"))


def _strike_panel(state: PDLCState, task: dict) -> tuple[int, dict]:
    """Convene the Strike Panel and return (chosen_index, panel_record).

    Under night-shift the recommended approach (index 0) is auto-picked.
    """
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    roster = ["neo", "echo", _domain_agent(task)]
    party = run_party(
        feature=feature,
        project_id=project_id,
        kind="strike-panel",
        topic=f"Diagnose the repeated failure of {task['external_id']} and propose fixes",
        roster=roster,
        context=f"3 auto-fix attempts failed for {task['external_id']} ({task.get('title')}).",
        night_shift_active=bool(state.get("night_shift_active")),
    )
    options = [
        {"index": 0, "name": "Approach 1 (recommended)", "by": "neo"},
        {"index": 1, "name": "Approach 2", "by": "echo"},
        {"index": 2, "name": "Escalate — take the wheel", "by": "human"},
    ]
    record = {
        "task_id": task["external_id"],
        "mom_ref": party.get("mom_ref"),
        "options": options,
    }

    if state.get("night_shift_active"):
        record["choice"] = 0
        record["auto"] = True
        return 0, record

    result = interrupt(
        {
            "kind": "user_input_required",
            "mode": "strike_panel",
            "task_id": task["external_id"],
            "questions": [f"Strike Panel for {task['external_id']}: pick an approach (0/1/2)"],
            "options": options,
            "mom_ref": party.get("mom_ref"),
        }
    )
    answers = result.get("answers") if isinstance(result, dict) else result
    try:
        choice = int(answers[0])
    except (TypeError, ValueError, IndexError):
        choice = 0
    record["choice"] = choice
    return choice, record


def _tdd_task(state: PDLCState, task: dict, test_loop: dict, strikes: list[dict]) -> dict:
    """Run red → green(+3-Strike) → refactor for one task. Returns a build record."""
    task_id = task["external_id"]

    # ── red ── write the failing test first.
    complete(_domain_agent(task), f"Write the failing test for {task_id}: {task.get('title')}")
    has_failing_test = True

    # ── green ── guard, then implement + auto-fix loop.
    assert_red_before_green(has_failing_test, task_id)
    fail_until = int(task.get("simulate_failures", 0) or 0)
    attempt = 0
    panel_record: dict | None = None
    while attempt < _MAX_ATTEMPTS:
        res = run_layer("unit", task_id, attempt=attempt, fail_until=fail_until)
        if res["passed"]:
            break
        attempt += 1
        test_loop[task_id] = attempt
        if attempt >= 3 and panel_record is None:
            _choice, panel_record = _strike_panel(state, task)
            strikes.append(panel_record)
            fail_until = 0  # chosen approach fixes it
            test_loop[task_id] = 0  # counter resets after human direction

    # ── refactor ── full unit layer stays green.
    refactor = run_layer("unit", task_id, attempt=attempt, fail_until=0)

    return {
        "task_id": task_id,
        "title": task.get("title"),
        "attempts": attempt,
        "struck": panel_record is not None,
        "passed": refactor["passed"],
        "status": "done",
    }


@instrumented_node("step.completed")
def build_loop(state: PDLCState) -> dict:
    """Walk every wave and build every task with the TDD micro-loop."""
    tasks = list(state.get("tasks") or [])
    by_id = {t["external_id"]: t for t in tasks}
    waves = compute_waves(tasks)

    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    night = bool(state.get("night_shift_active"))

    test_loop: dict = dict(state.get("test_loop") or {})
    strikes: list[dict] = list(state.get("strike_history") or [])
    build_log: list[dict] = list(state.get("build_log") or [])

    for wave_no, wave_ids in enumerate(waves, start=1):
        wave_tasks = [by_id[i] for i in wave_ids if i in by_id]
        # Wave Kickoff standup when the wave has parallel work.
        if len(wave_tasks) >= 2:
            run_party(
                feature=feature,
                project_id=project_id,
                kind="wave-kickoff",
                topic=f"Wave {wave_no} standup: surface hidden deps + ordering",
                roster=["neo", *{_domain_agent(t) for t in wave_tasks}],
                context=f"Wave {wave_no}: {', '.join(wave_ids)}",
                night_shift_active=night,
            )
        for task in wave_tasks:
            if _needs_roundtable(task):
                run_party(
                    feature=feature,
                    project_id=project_id,
                    kind="design-roundtable",
                    topic=f"Implementation approach for {task['external_id']}",
                    roster=["neo", "echo", _domain_agent(task)],
                    context=task.get("title", ""),
                    night_shift_active=night,
                )
            build_log.append(_tdd_task(state, task, test_loop, strikes))

    return {
        "sub_phase": "Build",
        "current_wave": len(waves),
        "current_task_id": None,
        "test_loop": test_loop,
        "strike_history": strikes,
        "build_log": build_log,
    }
