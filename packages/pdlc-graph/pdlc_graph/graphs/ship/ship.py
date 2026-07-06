"""Ship segment of the Operation loop (upstream skills/ship/steps/01-ship.md).

Pulse leads: compute the next semantic version, draft a CHANGELOG entry, pick a
deploy target (production is filtered out at selection), then open the merge +
deploy approval gate (#6, `merge_and_deploy_approve`). On approval the segment
merges to main (merge-commit only), records the deploy, and renders a
DEPLOYMENTS.md fragment.

    prepare -> merge_deploy_gate -> execute -> END

Compiled without an inner checkpointer so interrupts propagate to the composing
graph's checkpointer.
"""

from __future__ import annotations

from datetime import date as _date

from langgraph.graph import END, START, StateGraph

from ... import gates
from ...deploy_port import (
    assert_deploy_allowed,
    deploy,
    get_deploy_register,
    infer_tier,
    select_deploy_targets,
)
from ...instrumentation import evaluate, instrumented_node
from ...llm_port import complete
from ...ports import put_artifact
from ...render import render_changelog, render_deployments
from ...state import PDLCState
from ...vcs_port import merge_to_main
from ...versioning import next_version

GATE_KIND = "merge_and_deploy_approve"

__all__ = ["GATE_KIND", "build_ship", "ship_graph"]


def _slug(feature: str) -> str:
    return feature.strip().lower().replace(" ", "-") or "feature"


@instrumented_node("subphase.entered")
def prepare(state: PDLCState) -> dict:
    """Step 5-6/9 — compute version, draft CHANGELOG, pick the deploy target."""
    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    today = _date.today().isoformat()
    commits = state.get("commits") or []

    version = next_version(state.get("version"), commits)

    bullets = complete(
        "pulse",
        f"Draft a one-line CHANGELOG 'Added' bullet for shipping '{feature}' "
        f"({version}, {len(commits)} commit(s)).",
        system="PDLC release lead",
    ).strip()
    changelog_md = render_changelog(
        version=version,
        date=today,
        added=[bullets],
        changed=[],
        fixed=[],
        breaking=[],
    )
    path = f"docs/pdlc/memory/CHANGELOG_{version}_{today}.md"
    changelog_ref = put_artifact(project_id, path, changelog_md)

    candidates = select_deploy_targets(state.get("deploy_candidates") or ["staging"])
    deploy_target = candidates[0] if candidates else "staging"
    deploy_tier = infer_tier(deploy_target)

    # Phase J: prod-safety eval on the chosen target (no-op unless evals enabled).
    evaluate(
        "deploy", state, "", target="pulse",
        extra={"tier": deploy_tier, "target": deploy_target,
               "night_shift": bool(state.get("night_shift_active"))},
    )

    return {
        "version": version,
        "changelog_ref": changelog_ref,
        "deploy_target": deploy_target,
        "deploy_tier": deploy_tier,
    }


@instrumented_node("step.completed")
def merge_deploy_gate(state: PDLCState) -> dict:
    """Step 3 — open the merge + deploy approval gate; record the verdict."""
    payload = {
        "feature": state.get("feature"),
        "version": state.get("version"),
        "deploy_target": state.get("deploy_target"),
        "deploy_tier": state.get("deploy_tier"),
        "changelog_ref": state.get("changelog_ref"),
        "summary": "Approve to merge to main and deploy.",
    }
    verdict = gates.approval_gate(state, GATE_KIND, payload)
    return {"merge_and_deploy_approved": bool(verdict.get("approved"))}


@instrumented_node("subphase.exited")
def execute(state: PDLCState) -> dict:
    """Steps 7-9 — merge to main, record the deploy, render DEPLOYMENTS.md."""
    if not state.get("merge_and_deploy_approved"):
        return {"merged": False}

    feature = state.get("feature") or "untitled-feature"
    project_id = state.get("project_id") or "proj"
    today = _date.today().isoformat()
    version = state.get("version") or "v0.1.0"
    deploy_target = state.get("deploy_target") or "staging"
    deploy_tier = state.get("deploy_tier") or infer_tier(deploy_target)

    # Layer 2 of the prod-deploy ban — refuses a production tier under night-shift.
    assert_deploy_allowed(deploy_tier, night_shift=bool(state.get("night_shift_active")))

    merge = merge_to_main(
        feature=feature,
        version=version,
        description=f"Ship {feature} ({version})",
    )
    merge_sha = merge["sha"]

    # Execute the real deploy (a configured command/webhook, engine-side) and
    # record the URL it yields. With no deployer injected this is an honest
    # no-op that returns a labeled placeholder — never a fake *.example.app.
    result = deploy(env=deploy_target, ref=merge_sha, feature=feature)
    slug = _slug(feature)
    deploy_url = result.get("url") or (
        f"(simulated — no deploy performed for {slug})" if result.get("simulated")
        else f"https://{slug}.example.app")
    get_deploy_register().record(
        project_id,
        env=deploy_target,
        tier=deploy_tier,
        version=version,
        url=deploy_url,
        sha=merge_sha,
    )

    deployments_md = render_deployments(
        feature=feature,
        env=deploy_target,
        tier=deploy_tier,
        version=version,
        url=deploy_url,
        sha=merge_sha,
        date=today,
    )
    path = f"docs/pdlc/memory/DEPLOYMENTS_{deploy_target}_{today}.md"
    deployments_ref = put_artifact(project_id, path, deployments_md)

    return {
        "merged": True,
        "version": version,
        "deploy_target": deploy_target,
        "deploy_tier": deploy_tier,
        "deploy_url": deploy_url,
        "deployments_ref": deployments_ref,
    }


def build_ship() -> StateGraph:
    """Uncompiled Ship segment (START..prepare..gate..execute..END)."""
    g = StateGraph(PDLCState)
    g.add_node("prepare", prepare)
    g.add_node("merge_deploy_gate", merge_deploy_gate)
    g.add_node("execute", execute)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "merge_deploy_gate")
    g.add_edge("merge_deploy_gate", "execute")
    g.add_edge("execute", END)
    return g


ship_graph = build_ship().compile()
