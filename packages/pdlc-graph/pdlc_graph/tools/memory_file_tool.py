"""memory_file_* tools — read/write the 10 memory file kinds.

CONSTITUTION, STATE, INTENT, ROADMAP, DECISIONS, METRICS, OVERVIEW,
CHANGELOG, DEPLOYMENTS, EPISODE. Storage: S3 + `memory_files` row in
Postgres. Every read/write emits `tool.invoked` with `repository` set so
admin dashboards can pivot by repo.
"""

from typing import Literal

from langchain_core.tools import tool

MemoryKind = Literal[
    "CONSTITUTION", "STATE", "INTENT", "ROADMAP", "DECISIONS",
    "METRICS", "OVERVIEW", "CHANGELOG", "DEPLOYMENTS", "EPISODE",
]


@tool
def memory_read(project_id: str, kind: MemoryKind) -> str:
    """Read a memory file by kind."""
    return f"stub: memory_read({kind}) not yet wired"


@tool
def memory_write(project_id: str, kind: MemoryKind, content_ref: str) -> str:
    """Write a memory file. `content_ref` is an S3 key for the body (not the body itself)."""
    return f"stub: memory_write({kind}) not yet wired"
