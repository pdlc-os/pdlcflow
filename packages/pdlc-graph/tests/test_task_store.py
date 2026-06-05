"""Task store port — org_id threading, external_id preservation, atomic claim."""

from __future__ import annotations

from pdlc_graph.ports.tasks import InMemoryTaskStore


def test_create_mints_bd_ids_and_records_org():
    s = InMemoryTaskStore()
    a = s.create("org-1", "p1", "data model", "body", ["domain:backend"])
    b = s.create("org-1", "p1", "api", "body", ["domain:backend"])
    assert a == "bd-1" and b == "bd-2"
    rows = {t["external_id"]: t for t in s.list("p1")}
    assert rows["bd-1"]["org_id"] == "org-1"
    assert rows["bd-1"]["status"] == "open"


def test_create_preserves_supplied_external_id():
    s = InMemoryTaskStore()
    ext = s.create("org-1", "p1", "migrated", "body", [], external_id="bd-42")
    assert ext == "bd-42"
    assert s.list("p1")[0]["external_id"] == "bd-42"


def test_add_dependency_records_blockers():
    s = InMemoryTaskStore()
    s.create("o", "p1", "a", "", [])
    s.create("o", "p1", "b", "", [])
    s.add_dependency("p1", "bd-1", "bd-2")
    rows = {t["external_id"]: t for t in s.list("p1")}
    assert rows["bd-2"]["depends_on"] == ["bd-1"]


def test_claim_is_atomic_and_branch_unique():
    s = InMemoryTaskStore()
    s.create("o", "p1", "a", "", [])
    s.create("o", "p1", "b", "", [])
    assert s.claim("p1", "bd-1", "feat/x", "dev@acme") is True
    # Same branch can't be claimed by another task in the project.
    assert s.claim("p1", "bd-2", "feat/x", "dev@acme") is False
    # Already-claimed task can't be re-claimed.
    assert s.claim("p1", "bd-1", "feat/y", "dev@acme") is False
    rows = {t["external_id"]: t for t in s.list("p1")}
    assert rows["bd-1"]["branch"] == "feat/x" and rows["bd-1"]["status"] == "claimed"
    assert rows["bd-2"]["branch"] is None
