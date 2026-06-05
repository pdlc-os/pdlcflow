"""Construction pre-flight (upstream skills/build/steps/01-pre-flight.md).

Loads the tasks handed off by Inception's Plan sub-phase and derives the wave
order from their dependency graph. Sets the Build sub-phase and initialises the
3-Strike bookkeeping. Pure-ish: reads state, returns a patch.
"""

from __future__ import annotations

from ...instrumentation import instrumented_node
from ...state import PDLCState


def compute_waves(tasks: list[dict]) -> list[list[str]]:
    """Topological wave order from `depends_on`; honours a precomputed `wave`
    annotation when present (Plan's build_tree sets it)."""
    if not tasks:
        return []
    if all(t.get("wave") for t in tasks):
        max_wave = max(t["wave"] for t in tasks)
        return [
            [t["external_id"] for t in tasks if t.get("wave") == n]
            for n in range(1, max_wave + 1)
        ]

    by_id = {t["external_id"]: t for t in tasks}
    wave_of: dict[str, int] = {}

    def level(ext: str, seen: set[str]) -> int:
        if ext in wave_of:
            return wave_of[ext]
        if ext in seen:  # defensive cycle guard
            return 1
        seen.add(ext)
        deps = by_id.get(ext, {}).get("depends_on") or []
        lvl = 1 + max((level(d, seen) for d in deps if d in by_id), default=0)
        wave_of[ext] = lvl
        return lvl

    for t in tasks:
        level(t["external_id"], set())
    max_wave = max(wave_of.values())
    return [
        [t["external_id"] for t in tasks if wave_of[t["external_id"]] == n]
        for n in range(1, max_wave + 1)
    ]


@instrumented_node("subphase.entered")
def preflight(state: PDLCState) -> dict:
    """Enter Construction / Build; seed wave + strike bookkeeping."""
    return {
        "sub_phase": "Build",
        "current_wave": 1,
        "current_task_id": None,
        "test_loop": {},
        "strike_history": [],
        "build_log": [],
    }
