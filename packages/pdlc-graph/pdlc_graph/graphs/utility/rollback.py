"""/rollback — revert a shipped feature (Phase E utility).

Upstream skills/rollback: Atlas reverts a shipped feature to a prior version.
This node is the BOUNDED + hermetic graph form: it renders a rollback note,
persists it as an artifact (-> rollback_ref), and records a revert deploy in
the in-memory register so the deployments view reflects the rolled-back
version. Pure: no interrupt, no real git/deploy/network.
"""

from __future__ import annotations

from ...deploy_port import get_deploy_register, infer_tier
from ...instrumentation import instrumented_node
from ...ports import put_artifact
from ...render import render_rollback_note
from ...state import PDLCState


@instrumented_node("skill.invoked")
def rollback_node(state: PDLCState) -> dict:
    """Revert a shipped feature to `utility_args['to_version']`."""
    args = state.get("utility_args") or {}
    to_version = args.get("to_version") or "v0.0.0"
    reason = args.get("reason")

    feature = state.get("feature") or "feature"
    from_version = state.get("version") or "unknown"
    project_id = state.get("project_id") or "project"
    env = state.get("deploy_target") or "staging"
    tier = infer_tier(env)

    note = render_rollback_note(
        feature=feature,
        from_version=from_version,
        to_version=to_version,
        env=env,
        date=state.get("today") or "",
        reason=reason,
    )
    rollback_ref = put_artifact(project_id, "ROLLBACK.md", note)

    get_deploy_register().record(
        project_id,
        env=env,
        tier=tier,
        version=to_version,
        url="https://rollback",
        sha="rollback",
    )

    return {
        "rollback_ref": rollback_ref,
        "version": to_version,
        "utility_result": {
            "command": "rollback",
            "feature": feature,
            "from_version": from_version,
            "to_version": to_version,
            "env": env,
            "tier": tier,
            "rollback_ref": rollback_ref,
        },
    }
