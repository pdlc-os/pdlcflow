"""Phase H bundle 4 — migrations + RLS + admin.access.denied (hermetic parts).

The schema/RLS migrations + Postgres RLS are verified via docker-compose; here
we check the model metadata, the org-context SQL helper, and the cross-org
access guard.
"""

from __future__ import annotations

import pytest
from app.auth.local import resolve_org
from app.db.models import Base
from app.db.rls import set_org_context
from fastapi import HTTPException


def test_schema_metadata_has_core_tables():
    tables = set(Base.metadata.tables)
    for name in (
        "organizations", "users", "projects", "tasks", "memory_files",
        "approval_gates", "events", "org_llm_config", "agent_llm_config",
    ):
        assert name in tables
    assert len(tables) >= 13  # the 0001 migration creates all of these


def test_tasks_has_depends_on_column():
    assert "depends_on" in Base.metadata.tables["tasks"].columns


def test_set_org_context_issues_set_local():
    captured: dict = {}

    class FakeConn:
        def execute(self, stmt, params=None):
            captured["sql"] = str(stmt)
            captured["params"] = params

    set_org_context(FakeConn(), "org-123")
    assert "app.org_id" in captured["sql"]
    assert captured["params"] == {"v": "org-123"}


def test_resolve_org_allows_and_denies_when_auth_off():
    # auth off (principal=None): cross-org ban — org required, else 403.
    assert resolve_org(None, "org-1", "/admin/live") == "org-1"
    with pytest.raises(HTTPException) as exc:
        resolve_org(None, None, "/admin/live")
    assert exc.value.status_code == 403


def test_admin_access_denied_is_a_valid_event():
    from uuid import UUID

    from event_schema import EventEnvelope

    e = EventEnvelope(
        event_type="admin.access.denied",
        org_id=UUID(int=0),
        project_id=UUID(int=0),
        payload={"path": "/admin/live", "reason": "missing org_id"},
    )
    assert e.event_type == "admin.access.denied"
