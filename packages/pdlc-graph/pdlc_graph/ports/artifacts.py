"""Artifact store port — persists rendered markdown (PRD, MOM, design docs).

Default: in-memory. Engine injects a filesystem/S3-backed store.

Tenant isolation: artifacts are namespaced **{org_id}/{project_id}/{path}**. The
org is the authoritative tenant set per turn by the runner via `set_current_org`
(derived from the JWT-bound org when auth is on), NOT taken from the node call —
so a node can't write outside its tenant's prefix. `project_id` + `path` are
sanitized (no traversal, no absolute paths) before they reach the store; the
filesystem store additionally pins the resolved path under its base dir.

The returned URI is opaque to nodes; they stash it in state (e.g. `prd_ref`).
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Protocol

# Authoritative tenant for the current turn (runner sets it; default for direct
# calls / hermetic tests with no runner).
_current_org: ContextVar[str] = ContextVar("pdlc_artifact_org", default="default")

_SAFE_SEG = re.compile(r"^[A-Za-z0-9._@-]+$")  # one path segment (org / project / file)


def _safe_segment(s: str, kind: str) -> str:
    if not s or not _SAFE_SEG.match(s):
        raise ValueError(f"unsafe {kind} segment: {s!r}")
    return s


def safe_relpath(path: str) -> str:
    """Normalize a relative artifact path; reject absolute paths + traversal."""
    norm = path.replace("\\", "/")
    if norm.startswith("/"):
        raise ValueError(f"absolute artifact path not allowed: {path!r}")
    parts = [seg for seg in norm.split("/") if seg not in ("", ".")]
    if not parts or any(seg == ".." for seg in parts):
        raise ValueError(f"unsafe artifact path: {path!r}")
    return "/".join(parts)


def set_current_org(org_id: str | None):
    """Bind the tenant for artifact writes this turn; returns a reset token."""
    return _current_org.set(_safe_segment(org_id or "default", "org_id"))


def reset_current_org(token) -> None:
    _current_org.reset(token)


def current_org() -> str:
    return _current_org.get()


class ArtifactStore(Protocol):
    def put(self, org_id: str, project_id: str, path: str, content: str) -> str: ...
    def get(self, uri: str) -> str: ...


class InMemoryArtifactStore:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def put(self, org_id: str, project_id: str, path: str, content: str) -> str:
        uri = f"memory://{org_id}/{project_id}/{path}"
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
    """Persist `content` for the current tenant's `project_id` at `path`. The
    tenant (org) comes from the turn context — not the caller — so artifacts
    can't cross tenant boundaries even if a project_id is forged."""
    org = current_org()
    pid = _safe_segment(project_id, "project_id")
    rel = safe_relpath(path)
    return _store.put(org, pid, rel, content)


def get_artifact(uri: str) -> str:
    return _store.get(uri)
