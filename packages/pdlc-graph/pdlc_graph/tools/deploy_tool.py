"""deploy_* tools — persona-facing wrappers over the deploy port.

Delegates to `pdlc_graph.deploy_port`, the single source of truth for tier
inference and the three-layer production-deploy ban that the Operation Ship
sub-phase also uses.
"""

from langchain_core.tools import tool

from ..deploy_port import DeployBanError, assert_deploy_allowed, infer_tier


@tool
def deploy_run(environment: str, command: str, night_shift: bool = False) -> str:
    """Run a deploy command after tier inference + the production-deploy ban check."""
    tier = infer_tier(environment)
    try:
        assert_deploy_allowed(tier, night_shift=night_shift)
    except DeployBanError as exc:
        return f"blocked: {exc}"
    return f"deploy queued: env={environment} tier={tier} cmd={command!r}"
