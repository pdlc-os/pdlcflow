"""Persistence wiring — inject the configured backends into the ports at boot.

Each backend is flag-gated and falls back to the in-memory default if it can't
be constructed, so the engine always boots. Defaults (dev/test) leave every
port in-memory.
"""

from __future__ import annotations

import logging

from pdlc_graph.ports import set_artifact_store, set_task_store

from ..analytics import set_analytics_store
from .artifacts import FilesystemArtifactStore, S3ArtifactStore

log = logging.getLogger("pdlc.persistence")

__all__ = ["FilesystemArtifactStore", "S3ArtifactStore", "wire_persistence"]


def wire_persistence(settings) -> None:
    # --- artifact store ---
    kind = getattr(settings, "artifact_store", "memory")
    try:
        if kind == "filesystem":
            set_artifact_store(FilesystemArtifactStore(settings.artifact_dir))
            log.info("artifact store: filesystem (%s)", settings.artifact_dir)
        elif kind == "s3":
            set_artifact_store(
                S3ArtifactStore(
                    settings.s3_artifacts_bucket,
                    region=getattr(settings, "bedrock_region", None),
                    endpoint_url=getattr(settings, "s3_endpoint_url", None),
                )
            )
            log.info("artifact store: s3 (%s)", settings.s3_artifacts_bucket)
    except Exception as exc:  # pragma: no cover - prod-only path
        log.warning("artifact store '%s' unavailable (%s); using in-memory", kind, exc)

    # --- task store ---
    if getattr(settings, "task_store", "memory") == "postgres":
        try:
            from .tasks import PostgresTaskStore

            set_task_store(PostgresTaskStore(settings))
            log.info("task store: postgres")
        except Exception as exc:  # pragma: no cover - prod-only path
            log.warning("postgres task store unavailable (%s); using in-memory", exc)

    # --- analytics read store ---
    if getattr(settings, "analytics_backend", "memory") == "postgres":
        try:
            from ..analytics.postgres_store import PostgresAnalyticsStore

            set_analytics_store(PostgresAnalyticsStore(settings))
            log.info("analytics backend: postgres")
        except Exception as exc:  # pragma: no cover - prod-only path
            log.warning("postgres analytics unavailable (%s); using in-memory", exc)
