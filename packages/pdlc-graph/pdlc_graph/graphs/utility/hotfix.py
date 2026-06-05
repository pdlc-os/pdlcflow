"""/hotfix — emergency compressed build->ship (Phase E utility).

Upstream skills/hotfix: Pulse takes the lead for a production emergency,
skipping inception/design and running a compressed build->ship. This node is
the BOUNDED + hermetic graph form: ONE human confirmation via interrupt()
before shipping, then a recorded deploy plus a compact hotfix record artifact
(-> hotfix_ref). Under night-shift it auto-proceeds (no interrupt). The
production-deploy ban (assert_deploy_allowed) still applies.
"""

from __future__ import annotations

from langgraph.types import interrupt

from ...deploy_port import assert_deploy_allowed, get_deploy_register, infer_tier
from ...instrumentation import instrumented_node
from ...ports import put_artifact
from ...render import render_hotfix_record
from ...state import PDLCState


@instrumented_node("skill.invoked")
def hotfix_node(state: PDLCState) -> dict:
    """Run a compressed, single-confirmation emergency hotfix deploy."""
    args = state.get("utility_args") or {}
    summary = args.get("summary") or "emergency hotfix"

    night_shift = bool(state.get("night_shift_active"))

    # ── single human confirmation (skipped under night-shift) ──
    if night_shift:
        proceed = True
        auto = True
    else:
        verdict = interrupt(
            {
                "kind": "user_input_required",
                "mode": "hotfix_confirm",
                "questions": ["Confirm emergency hotfix deploy?"],
                "summary": summary,
            }
        )
        proceed = _is_confirmed(verdict)
        auto = False

    if not proceed:
        return {
            "utility_result": {"command": "hotfix", "aborted": True},
        }

    project_id = state.get("project_id") or "project"
    feature = state.get("feature") or "feature"
    env = state.get("deploy_target") or "staging"
    tier = infer_tier(env)
    version = state.get("version") or "v0.0.0"

    # Layer-2 production-deploy ban — still enforced in hotfix mode.
    assert_deploy_allowed(tier, night_shift=night_shift)

    get_deploy_register().record(
        project_id,
        env=env,
        tier=tier,
        version=version,
        url="https://hotfix",
        sha="hotfix",
    )

    record = render_hotfix_record(
        summary=summary,
        version=version,
        env=env,
        tier=tier,
        date=state.get("today") or "",
        auto=auto,
    )
    hotfix_ref = put_artifact(project_id, "HOTFIX.md", record)

    return {
        "hotfix_ref": hotfix_ref,
        "utility_result": {
            "command": "hotfix",
            "shipped": True,
            "feature": feature,
            "summary": summary,
            "env": env,
            "tier": tier,
            "version": version,
            "auto": auto,
            "hotfix_ref": hotfix_ref,
        },
    }


def _is_confirmed(verdict: object) -> bool:
    """Interpret a resume payload as a yes/no confirmation."""
    if isinstance(verdict, bool):
        return verdict
    if isinstance(verdict, dict):
        if "confirmed" in verdict:
            return bool(verdict["confirmed"])
        if "approved" in verdict:
            return bool(verdict["approved"])
        answers = verdict.get("answers")
        if isinstance(answers, (list, tuple)) and answers:
            verdict = answers[0]
    if isinstance(verdict, str):
        return verdict.strip().lower() in {"yes", "y", "confirm", "true", "ok"}
    return bool(verdict)
