"""Push a Manifest to a running pdlc-engine."""

from __future__ import annotations

from .scan import Manifest


def push_manifest(_m: Manifest, _engine_url: str) -> dict[str, int]:
    """Phase A stub. Real implementation:
      - upload each memory file body to S3, then POST a row into memory_files
      - parse each episode for metrics → episodes row
      - read bd-NN external IDs → tasks row preserving external_id
      - read DECISIONS.md → decisions rows
      - read DEPLOYMENTS.md → deployments rows
      - read pdlc-night-shift.json → night_shift_runs row (if status terminal)
    All POSTs are idempotent (server upserts on content_sha for memory_files
    and on external_id for tasks).
    """
    return {"memory_files": 0, "episodes": 0, "tasks": 0,
            "decisions": 0, "deployments": 0, "night_shift_runs": 0}
