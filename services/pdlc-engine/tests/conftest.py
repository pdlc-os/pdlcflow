"""Shared fixtures — reset the runtime + graph ports between tests so each
test gets a fresh MemorySaver, gate store, event bus, and artifact/task stores.
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.integration tests unless PDLC_RUN_INTEGRATION is set
    (they need live Postgres/Redis/MinIO — the integration CI job sets it)."""
    if os.getenv("PDLC_RUN_INTEGRATION"):
        return
    skip = pytest.mark.skip(reason="integration: set PDLC_RUN_INTEGRATION=1 (needs live infra)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _reset_runtime():
    from app.analytics import reset_analytics_store
    from app.runtime import reset_dispatcher, reset_runner, reset_runtime_ports
    from pdlc_graph.ports import reset_artifact_store, reset_task_store

    reset_runtime_ports()
    reset_runner()
    reset_dispatcher()
    reset_artifact_store()
    reset_task_store()
    reset_analytics_store()
    yield
