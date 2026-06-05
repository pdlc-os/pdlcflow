"""Pure markdown renderers for Inception artifacts.

Every function here is a pure (state/dict -> str) transform with no I/O, so
artifact content is unit-testable without S3 or a model. Nodes call a
renderer, then `ports.put_artifact(...)` to persist the returned string.
"""

from .design import (
    render_api_contracts,
    render_architecture,
    render_data_model,
    render_threat_model,
    render_ux_review,
)
from .discovery import render_discovery_summary
from .mom import render_mom
from .plan import render_plan
from .prd import render_prd

__all__ = [
    "render_api_contracts",
    "render_architecture",
    "render_data_model",
    "render_discovery_summary",
    "render_mom",
    "render_plan",
    "render_prd",
    "render_threat_model",
    "render_ux_review",
]
