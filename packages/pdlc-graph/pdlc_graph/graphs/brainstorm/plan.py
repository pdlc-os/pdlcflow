"""PLAN sub-phase (upstream skills/brainstorm/steps/04-plan.md, steps 13-19).

Step 13 — decompose the approved PRD + design into discrete, implementable
tasks. Neo proposes via `complete()`, but the task list itself is produced
deterministically (one coherent unit of work each, RFC-2119-style domains).
Step 14 — create every task through the task-store port, capturing the
`bd-NN` external ids into `state["tasks"]`.
Step 15 — declare dependencies (blocker → blocked) on the store.
Step 16 — compute the wave order and the Mermaid dependency tree.
Step 17 — render the plan file via `render_plan` and persist it -> `plan_ref`.
Step 18 — open the `beads_tasklist_approve` gate -> `plan_approved`.
Step 19 — wrap-up handoff patch.

Graph shape: START -> decompose -> create_tasks -> declare_deps -> build_tree
-> render_plan_file -> plan_gate -> wrap_up -> END. Compiled without a
checkpointer for composition; tests compile with a MemorySaver.
"""

from __future__ import annotations

from datetime import date as _date

from langgraph.graph import END, START, StateGraph

from ... import gates
from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...ports import get_task_store, put_artifact
from ...render import render_plan
from ...state import PDLCState
from ...visual import mermaid_screen, visual

GATE_KIND = "beads_tasklist_approve"

# The deterministic task skeleton: one coherent unit of work each, in
# dependency order. `deps` are indices into this list (resolved to bd-NN
# external ids once the tasks are created).
_SKELETON: list[dict] = [
    {
        "slug": "data-model",
        "title": "Data model & migration",
        "domain": "backend",
        "deps": [],
        "intent": "the persistence schema and migration",
    },
    {
        "slug": "api",
        "title": "Service logic & API endpoint",
        "domain": "backend",
        "deps": [0],
        "intent": "the service method and API endpoint",
    },
    {
        "slug": "ui",
        "title": "UI component & wiring",
        "domain": "frontend",
        "deps": [1],
        "intent": "the user-facing component wired to the API",
    },
    {
        "slug": "tests",
        "title": "Integration tests & CI",
        "domain": "devops",
        "deps": [1, 2],
        "intent": "end-to-end tests and CI coverage",
    },
]


def _slug(feature: str) -> str:
    return feature.strip().lower().replace(" ", "-") or "feature"


def _draft_body(feature: str, intent: str) -> str:
    """One Neo completion drafting an implementation note for a task."""
    prompt = (
        f"Draft a concise implementation task for {intent} of the feature "
        f"'{feature}'. Reference the PRD acceptance criteria; note what the "
        f"implementing agent will need."
    )
    return complete("neo", prompt, system="PDLC task author").strip()


def _compute_waves(tasks: list[dict]) -> list[list[str]]:
    """Topological wave order: a task's wave is 1 + max(dep waves)."""
    wave_of: dict[str, int] = {}

    def level(ext: str, by_id: dict[str, dict], seen: set[str]) -> int:
        if ext in wave_of:
            return wave_of[ext]
        if ext in seen:  # defensive cycle guard
            return 1
        seen.add(ext)
        deps = by_id[ext].get("depends_on") or []
        lvl = 1 + max((level(d, by_id, seen) for d in deps), default=0)
        wave_of[ext] = lvl
        return lvl

    by_id = {t["external_id"]: t for t in tasks}
    for t in tasks:
        level(t["external_id"], by_id, set())

    waves: list[list[str]] = []
    if not wave_of:
        return waves
    for n in range(1, max(wave_of.values()) + 1):
        waves.append([ext for ext in (t["external_id"] for t in tasks) if wave_of[ext] == n])
    return waves


def _mermaid_tree(tasks: list[dict]) -> str:
    """Render the dependency tree as a Mermaid `graph TD` block (blocker -> blocked)."""
    lines = ["graph TD"]
    for t in tasks:
        ext = t["external_id"]
        title = (t.get("title") or "").replace('"', "'")
        lines.append(f'    {ext}["{ext}: {title}"]')
    for t in tasks:
        for dep in t.get("depends_on") or []:
            lines.append(f"    {dep} --> {t['external_id']}")
    return "\n".join(lines)


@instrumented_node("subphase.entered")
def decompose(state: PDLCState) -> dict:
    """Step 13 — propose a deterministic task list from PRD + design."""
    feature = state.get("feature") or "untitled-feature"
    slug = _slug(feature)
    specs: list[dict] = []
    for item in _SKELETON:
        specs.append(
            {
                "title": f"{feature}: {item['title']}",
                "body": _draft_body(feature, item["intent"]),
                "labels": [f"epic:{slug}", "story:US-001", f"domain:{item['domain']}"],
                "deps": list(item["deps"]),
            }
        )
    return {"tasks": specs}


@instrumented_node("step.completed")
def create_tasks(state: PDLCState) -> dict:
    """Step 14 — create each task, capturing bd-NN external ids."""
    org_id = state.get("org_id") or "self-host"
    project_id = state.get("project_id") or "proj"
    store = get_task_store()
    specs = state.get("tasks") or []

    ext_by_idx: dict[int, str] = {}
    for i, spec in enumerate(specs):
        ext_by_idx[i] = store.create(
            org_id, project_id, spec["title"], spec.get("body", ""), spec.get("labels", [])
        )

    created: list[dict] = []
    for i, spec in enumerate(specs):
        created.append(
            {
                "external_id": ext_by_idx[i],
                "title": spec["title"],
                "body": spec.get("body", ""),
                "labels": spec.get("labels", []),
                "depends_on": [ext_by_idx[d] for d in spec.get("deps", [])],
            }
        )
    return {"tasks": created}


@instrumented_node("step.completed")
def declare_deps(state: PDLCState) -> dict:
    """Step 15 — declare each dependency (blocker -> blocked) on the store."""
    org_id = state.get("org_id") or "self-host"
    project_id = state.get("project_id") or "proj"
    store = get_task_store()
    tasks = state.get("tasks") or []
    for t in tasks:
        for blocker in t.get("depends_on") or []:
            store.add_dependency(org_id, project_id, blocker, t["external_id"])
    return {"tasks": tasks}


@instrumented_node("step.completed")
def build_tree(state: PDLCState) -> dict:
    """Step 16 — compute the wave order + Mermaid tree; annotate tasks with waves."""
    tasks = state.get("tasks") or []
    waves = _compute_waves(tasks)
    _mermaid_tree(tasks)  # built here for fidelity; re-derived deterministically at render
    wave_of = {ext: n for n, wave in enumerate(waves, start=1) for ext in wave}
    annotated = [{**t, "wave": wave_of.get(t["external_id"])} for t in tasks]
    return {"tasks": annotated}


@instrumented_node("subphase.exited")
def render_plan_file(state: PDLCState) -> dict:
    """Step 17 — render the plan file and persist it -> plan_ref."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    today = _date.today().isoformat()
    tasks = state.get("tasks") or []

    waves = _compute_waves(tasks)
    mermaid = _mermaid_tree(tasks)
    plan_md = render_plan(
        feature=feature,
        date=today,
        prd_ref=state.get("prd_ref"),
        tasks=tasks,
        mermaid=mermaid,
        waves=waves,
    )

    slug = _slug(feature)
    path = f"docs/pdlc/prds/plans/plan_{slug}_{today}.md"
    plan_ref = put_artifact(project_id, path, plan_md)
    return {"plan_ref": plan_ref}


@instrumented_node("step.completed")
def plan_gate(state: PDLCState) -> dict:
    """Step 18 — open the plan approval gate; record the verdict."""
    tasks = state.get("tasks") or []
    waves = _compute_waves(tasks)
    payload = {
        "feature": state.get("feature"),
        "plan_ref": state.get("plan_ref"),
        "task_count": len(tasks),
        "wave_count": len(waves),
        "summary": f"{len(tasks)} tasks in {len(waves)} waves ready for review.",
        # Visual companion: render the wave dependency tree beside the gate.
        "visual": visual(
            [
                mermaid_screen(
                    f"Task dependency graph — {state.get('feature') or 'feature'}",
                    _mermaid_tree(tasks),
                    subtitle="Wave-based execution order; same-wave tasks run in parallel.",
                )
            ]
        ),
    }
    verdict = gates.approval_gate(state, GATE_KIND, payload)
    return {"plan_approved": bool(verdict.get("approved"))}


@instrumented_node("step.completed")
def wrap_up(state: PDLCState) -> dict:
    """Step 19 — wrap-up handoff patch for the Construction phase."""
    feature = state.get("feature")
    tasks = state.get("tasks") or []
    handoff = {
        "phase_completed": "Inception / Plan",
        "next_phase": "Construction / Build",
        "feature": feature,
        "key_outputs": [ref for ref in (state.get("prd_ref"), state.get("plan_ref")) if ref],
        "decisions_made": [f"{len(tasks)} tasks created across {len(_compute_waves(tasks))} waves"],
        "next_action": "Start Construction — run /build",
        "pending_questions": [],
    }
    return {"sub_phase": "Plan", "handoff": handoff}


def build_plan() -> StateGraph:
    """Uncompiled PLAN graph over PDLCState (START..steps..gate..END)."""
    g = StateGraph(PDLCState)
    g.add_node("decompose", decompose)
    g.add_node("create_tasks", create_tasks)
    g.add_node("declare_deps", declare_deps)
    g.add_node("build_tree", build_tree)
    g.add_node("render_plan_file", render_plan_file)
    g.add_node("plan_gate", plan_gate)
    g.add_node("wrap_up", wrap_up)
    g.add_edge(START, "decompose")
    g.add_edge("decompose", "create_tasks")
    g.add_edge("create_tasks", "declare_deps")
    g.add_edge("declare_deps", "build_tree")
    g.add_edge("build_tree", "render_plan_file")
    g.add_edge("render_plan_file", "plan_gate")
    g.add_edge("plan_gate", "wrap_up")
    g.add_edge("wrap_up", END)
    return g


plan_graph = build_plan().compile()
