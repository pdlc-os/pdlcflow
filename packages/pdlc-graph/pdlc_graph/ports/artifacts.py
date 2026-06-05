"""Artifact store port — persists rendered markdown (PRD, MOM, design docs).

Default: in-memory. Engine injects an S3-backed store that also writes a
`memory_files` row. The returned URI is opaque to nodes; they stash it in
state (e.g. `prd_ref`) and pass it to approval-gate payloads.
"""

from __future__ import annotations

from typing import Protocol


class ArtifactStore(Protocol):
    def put(self, project_id: str, path: str, content: str) -> str: ...
    def get(self, uri: str) -> str: ...


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def put(self, project_id: str, path: str, content: str) -> str:
        uri = f"memory://{project_id}/{path}"
        self._store[uri] = content
        return uri

    def get(self, uri: str) -> str:
        return self._store[uri]


_store: ArtifactStore = InMemoryArtifactStore()


def set_artifact_store(store: ArtifactStore) -> None:
    global _store
    _store = store


def reset_artifact_store() -> None:
    global _store
    _store = InMemoryArtifactStore()


def put_artifact(project_id: str, path: str, content: str) -> str:
    return _store.put(project_id, path, content)


def get_artifact(uri: str) -> str:
    return _store.get(uri)
