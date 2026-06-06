"""Reflect sub-phase (upstream skills/ship/steps/03-reflect.md, gate #8).

Jarvis leads the retrospective. The segment synthesises a retro grounded in the
build log, construction test results, and review package; renders the permanent
episode file and opens the episode_approve gate; then renders a metrics rollup
and wraps the Operation loop up (releases the roadmap claim, sets
operation_complete, writes the Idle handoff).

Nodes: retro_and_episode -> episode_gate -> metrics_and_wrapup.
Compiled without an inner checkpointer so interrupts propagate to the top-level
graph's checkpointer.
"""

from __future__ import annotations

from datetime import date as _date

from langgraph.graph import END, START, StateGraph

from ... import gates
from ...instrumentation import evaluate, instrumented_node
from ...llm_port import complete
from ...ports import put_artifact
from ...render import render_episode, render_metrics
from ...state import PDLCState

GATE_KIND = "episode_approve"


def _slug(feature: str) -> str:
    return feature.strip().lower().replace(" ", "-") or "feature"


@instrumented_node("subphase.entered")
def retro_and_episode(state: PDLCState) -> dict:
    """Steps 13-14 — synthesise the retro and render/persist the episode file."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    today = _date.today().isoformat()
    episode_id = state.get("episode_id") or "001"

    build_log = state.get("build_log") or []
    test_results = state.get("construction_test_results") or {}
    review_ref = state.get("review_ref")

    # Jarvis synthesises the retro grounded in the construction artifacts.
    grounding = (
        f"Feature: {feature}\n"
        f"Tasks built: {len(build_log)}\n"
        f"Test layers: {', '.join(sorted(test_results)) or 'none'}\n"
        f"Review: {review_ref or 'none'}\n"
    )
    well = complete(
        "jarvis",
        f"Write one 'what went well' observation for the retro.\n{grounding}",
        system="PDLC tech writer leading the Reflect retrospective",
    ).strip()
    broke = complete(
        "jarvis",
        f"Write one 'what broke or slowed us down' observation.\n{grounding}",
        system="PDLC tech writer leading the Reflect retrospective",
    ).strip()
    improve = complete(
        "jarvis",
        f"Write one 'what to improve next time' observation.\n{grounding}",
        system="PDLC tech writer leading the Reflect retrospective",
    ).strip()
    reflect_notes = {"went_well": [well], "broke": [broke], "improve": [improve]}

    passed = sum(1 for r in test_results.values() if isinstance(r, dict) and r.get("passed"))
    test_summary = (
        f"{passed}/{len(test_results)} layers passed "
        f"({', '.join(sorted(test_results)) or 'no layers recorded'})."
    )

    links: dict[str, str] = {}
    if review_ref:
        links["Review file"] = review_ref
    if state.get("deployments_ref"):
        links["Deployments"] = state["deployments_ref"]
    if state.get("deploy_url"):
        links["Deploy URL"] = state["deploy_url"]

    decisions = [f"Shipped {state.get('version') or 'unversioned'} of {feature}."]
    agent_team = [
        "Neo (Architect)",
        "Echo (QA Engineer)",
        "Phantom (Security Reviewer)",
        "Jarvis (Tech Writer)",
        "Pulse (DevOps)",
    ]

    episode_md = render_episode(
        feature=feature,
        episode_id=episode_id,
        date=today,
        what_was_built=complete(
            "jarvis",
            f"Summarise in 3-4 sentences what was built and shipped.\n{grounding}",
            system="PDLC tech writer",
        ).strip(),
        links=links,
        decisions=decisions,
        test_summary=test_summary,
        tradeoffs=[],
        agent_team=agent_team,
        reflect_notes=reflect_notes,
    )
    path = f"docs/pdlc/memory/episodes/{episode_id}_{_slug(feature)}_{today}.md"
    episode_ref = put_artifact(project_id, path, episode_md)

    # Phase J: score the episode/retro output (no-op unless evals enabled).
    evaluate("episode", state, episode_md, target="atlas", sources={"feature": feature})

    return {"sub_phase": "Reflect", "episode_ref": episode_ref}


@instrumented_node("step.completed")
def episode_gate(state: PDLCState) -> dict:
    """Step 15 — open the episode_approve gate (#8); record the verdict."""
    payload = {
        "feature": state.get("feature"),
        "episode_ref": state.get("episode_ref"),
        "summary": "Episode file ready; approve to commit it to the repository.",
    }
    verdict = gates.approval_gate(state, GATE_KIND, payload)
    return {"episode_approved": bool(verdict.get("approved"))}


@instrumented_node("subphase.exited")
def metrics_and_wrapup(state: PDLCState) -> dict:
    """Steps 16g-18 — render the metrics rollup, then wrap the Operation loop."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    today = _date.today().isoformat()
    episode_id = state.get("episode_id") or "001"

    build_log = state.get("build_log") or []
    test_results = state.get("construction_test_results") or {}
    passed = sum(1 for r in test_results.values() if isinstance(r, dict) and r.get("passed"))
    test_pass_pct = round(100.0 * passed / len(test_results), 1) if test_results else 100.0
    strikes = len(state.get("strike_history") or [])

    metrics_md = render_metrics(
        feature=feature,
        episode_id=episode_id,
        date=today,
        cycle_days=state.get("cycle_days") or 1,
        test_pass_pct=test_pass_pct,
        review_rounds=1,
        strikes=strikes,
        tasks=len(build_log),
    )
    path = f"docs/pdlc/memory/METRICS_{_slug(feature)}_{today}.md"
    metrics_ref = put_artifact(project_id, path, metrics_md)

    handoff = {
        "phase_completed": "Operation",
        "next_phase": "Idle",
        "feature": feature,
        "key_outputs": [ref for ref in (state.get("episode_ref"), metrics_ref) if ref],
        "decisions_made": [f"Episode {episode_id} committed; roadmap claim released."],
        "next_action": "Run /brainstorm for the next feature",
        "pending_questions": [],
    }

    return {
        "metrics_ref": metrics_ref,
        "operation_complete": True,
        "roadmap_claim": None,
        "handoff": handoff,
        "sub_phase": "Reflect",
    }


def build_reflect() -> StateGraph:
    """Uncompiled Reflect graph (START..steps..gate..END)."""
    g = StateGraph(PDLCState)
    g.add_node("retro_and_episode", retro_and_episode)
    g.add_node("episode_gate", episode_gate)
    g.add_node("metrics_and_wrapup", metrics_and_wrapup)
    g.add_edge(START, "retro_and_episode")
    g.add_edge("retro_and_episode", "episode_gate")
    g.add_edge("episode_gate", "metrics_and_wrapup")
    g.add_edge("metrics_and_wrapup", END)
    return g


reflect_graph = build_reflect().compile()
