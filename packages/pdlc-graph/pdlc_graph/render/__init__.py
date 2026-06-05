"""Pure markdown renderers for Inception artifacts.

Every function here is a pure (state/dict -> str) transform with no I/O, so
artifact content is unit-testable without S3 or a model. Nodes call a
renderer, then `ports.put_artifact(...)` to persist the returned string.
"""

from .changelog import render_changelog
from .deployments import render_deployments
from .design import (
    render_api_contracts,
    render_architecture,
    render_data_model,
    render_threat_model,
    render_ux_review,
)
from .discovery import render_discovery_summary
from .episode import render_episode
from .metrics import render_metrics
from .mom import render_mom
from .plan import render_plan
from .prd import render_prd
from .review import render_review

__all__ = [
    "render_api_contracts",
    "render_architecture",
    "render_changelog",
    "render_data_model",
    "render_deployments",
    "render_discovery_summary",
    "render_episode",
    "render_metrics",
    "render_mom",
    "render_plan",
    "render_prd",
    "render_review",
    "render_threat_model",
    "render_ux_review",
]
