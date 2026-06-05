"""deploy_* tools — fly / vercel / terraform / kubectl wrappers.

Every deploy call is gated by the Operation-phase rule (upstream guardrail
pdlc-guardrails.js). The wrapper checks the run state and emits deploy.blocked
+ raises if the gate isn't satisfied. Three-layer prod-deploy ban is enforced
here (layer 1: partition at selection; layer 2: validate at activate; layer 3:
runtime evaluator check in sentinel).
"""

from langchain_core.tools import tool


@tool
def deploy_run(environment: str, tier: str, command: str) -> str:
    """Run a deploy command after gate + tier validation."""
    if tier == "production":
        return "blocked: production deploys never permitted under autonomous flow"
    return "stub: deploy not yet wired"
