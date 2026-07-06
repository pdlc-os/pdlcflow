"""Pure markdown renderers for Inception artifacts.

Every function here is a pure (state/dict -> str) transform with no I/O, so
artifact content is unit-testable without S3 or a model. Nodes call a
renderer, then `ports.put_artifact(...)` to persist the returned string.
"""

from .changelog import render_changelog
from .decisions import render_decisions
from .deployments import render_deployments
from .design import (
    render_api_contracts,
    render_architecture,
    render_data_model,
    render_threat_model,
    render_ux_review,
)
from .discovery import render_discovery_summary
from .doctor import render_doctor
from .episode import render_episode
from .hotfix import render_hotfix_record
from .initialization import render_constitution, render_intent, render_roadmap
from .metrics import render_metrics
from .mom import render_mom
from .plan import render_plan
from .prd import render_prd
from .review import render_review
from .rollback import render_rollback_note

__all__ = [
    "render_api_contracts",
    "render_architecture",
    "render_changelog",
    "render_constitution",
    "render_data_model",
    "render_decisions",
    "render_deployments",
    "render_discovery_summary",
    "render_doctor",
    "render_episode",
    "render_hotfix_record",
    "render_intent",
    "render_metrics",
    "render_mom",
    "render_plan",
    "render_prd",
    "render_review",
    "render_roadmap",
    "render_rollback_note",
    "render_threat_model",
    "render_ux_review",
]
