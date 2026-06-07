"""Injectable side-effect ports for the graph package.

Each port has an in-memory default so the Inception graph runs hermetically
in tests. The engine injects S3-backed / Postgres-backed implementations at
boot via the `set_*` functions.
"""

from .artifacts import (
    InMemoryArtifactStore,
    current_org,
    get_artifact,
    put_artifact,
    reset_artifact_store,
    reset_current_org,
    set_artifact_store,
    set_current_org,
)
from .tasks import (
    InMemoryTaskStore,
    get_task_store,
    reset_task_store,
    set_task_store,
)

__all__ = [
    "InMemoryArtifactStore",
    "InMemoryTaskStore",
    "current_org",
    "get_artifact",
    "get_task_store",
    "put_artifact",
    "reset_artifact_store",
    "reset_current_org",
    "reset_task_store",
    "set_artifact_store",
    "set_current_org",
    "set_task_store",
]
