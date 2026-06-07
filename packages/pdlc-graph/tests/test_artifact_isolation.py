"""Artifact tenant isolation — org-namespacing via the turn context + sanitization."""

from __future__ import annotations

import pytest
from pdlc_graph.ports import (
    get_artifact,
    put_artifact,
    reset_current_org,
    set_current_org,
)


def test_org_comes_from_context_not_the_caller():
    # Same project_id + path under two different tenants → distinct, non-colliding uris.
    tok = set_current_org("org-A")
    a = put_artifact("proj-1", "docs/PRD.md", "A content")
    reset_current_org(tok)
    tok = set_current_org("org-B")
    b = put_artifact("proj-1", "docs/PRD.md", "B content")
    reset_current_org(tok)

    assert a != b
    assert "org-A/proj-1" in a and "org-B/proj-1" in b
    assert get_artifact(a) == "A content" and get_artifact(b) == "B content"


def test_default_tenant_when_no_context():
    assert "default/" in put_artifact("proj-x", "f.md", "x")


def test_path_traversal_is_rejected():
    tok = set_current_org("org-A")
    try:
        for bad in ("../escape.md", "a/../../etc/passwd", "/abs/path.md"):
            with pytest.raises(ValueError):
                put_artifact("proj-1", bad, "nope")
    finally:
        reset_current_org(tok)


def test_unsafe_project_id_is_rejected():
    tok = set_current_org("org-A")
    try:
        with pytest.raises(ValueError):
            put_artifact("../other-tenant", "f.md", "nope")
    finally:
        reset_current_org(tok)
