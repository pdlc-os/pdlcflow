"""Shared fixtures — reset the runtime + graph ports between tests so each
test gets a fresh MemorySaver, gate store, event bus, and artifact/task stores.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_runtime():
    from app.runtime import reset_dispatcher, reset_runner, reset_runtime_ports
    from pdlc_graph.ports import reset_artifact_store, reset_task_store

    reset_runtime_ports()
    reset_runner()
    reset_dispatcher()
    reset_artifact_store()
    reset_task_store()
    yield
