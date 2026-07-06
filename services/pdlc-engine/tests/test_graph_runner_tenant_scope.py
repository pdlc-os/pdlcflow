"""Regression: the runner must reconcile a turn's pending interrupt WHILE the
turn's tenant is still bound.

The bug: `_advance` read pending via `_sync_pending` (→ checkpointer `get_state`)
*after* the `finally` reset `current_org` to "default". With the RLS-FORCEd
Postgres checkpointer the tenant pool stamps `app.org_id = current_org()`, and
the checkpoint-table policy is `thread_id like app.org_id || ':%'`. Read with
org="default", the policy hid the thread's own `__interrupt__` writes, so every
gate/question turn came back `pending=None` and looked "completed" — the whole
interactive flow silently died on the durable checkpointer. (MemorySaver has no
RLS, so it — and every hermetic test — masked it.)

This guards the ordering invariant hermetically: at the moment pending is read,
`current_org()` is the thread's org, not "default".
"""

from __future__ import annotations

from app.runtime.graph_runner import GraphRunner
from pdlc_graph.ports import current_org


class _StubGraph:
    def invoke(self, *a, **k):  # a turn that does nothing
        return None


def test_pending_is_read_while_tenant_is_bound():
    runner = GraphRunner.__new__(GraphRunner)  # skip the heavy meta-graph build
    runner._graph = _StubGraph()
    runner._bind_execution_context = lambda *a, **k: None  # avoid get_state

    seen: dict = {}

    def _spy_sync_pending(thread_id, cfg):
        seen["org_at_read"] = current_org()  # capture the tenant bound at read time
        return None

    runner._sync_pending = _spy_sync_pending
    runner._advance("org-abc:proj-1:sess-1", {"feature": "x"})

    # Must be the thread's org — NOT "default" (which RLS would filter to nothing).
    assert seen["org_at_read"] == "org-abc"


def test_tenant_context_is_torn_down_after_the_turn():
    runner = GraphRunner.__new__(GraphRunner)
    runner._graph = _StubGraph()
    runner._bind_execution_context = lambda *a, **k: None
    runner._sync_pending = lambda thread_id, cfg: None

    runner._advance("org-xyz:proj:sess", {"feature": "y"})
    assert current_org() == "default"  # reset in the finally, no leak across turns
