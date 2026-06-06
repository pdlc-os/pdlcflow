"""Integration test — the full Inception graph (Discover→Define→Design→Plan).

Proves the four sub-phase subgraphs compose under one parent and that
`interrupt()` sites propagate to the top-level checkpointer. Night-shift mode
drives the whole chain to completion with no human turns; a second test drives
the human path through the first two gates to confirm interrupts surface from
nested subgraphs.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.graphs.brainstorm import build_brainstorm
from pdlc_graph.ports import get_task_store, reset_artifact_store, reset_task_store


@pytest.fixture(autouse=True)
def _hermetic():
    reset_artifact_store()
    reset_task_store()
    yield
    reset_artifact_store()
    reset_task_store()


def _initial(**overrides) -> dict:
    base = {
        "feature": "saved searches",
        "project_id": "proj-1",
        "interaction_mode": "sketch",
        "brainstorm_log": [],
    }
    base.update(overrides)
    return base


def test_night_shift_runs_all_four_subphases():
    g = build_brainstorm().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}

    out = g.invoke(_initial(night_shift_active=True), cfg)
    assert g.get_state(cfg).next == ()  # ran to completion

    # Each sub-phase left its mark.
    assert out["discovery_summary"]
    assert out["party_results"]["discover_summary"]["approved"] is True
    assert out["prd_ref"] and out["prd_approved"] is True
    assert out["design_docs"]["architecture"] and out["design_approved"] is True
    assert out["threat_model_ref"] and out["ux_review_ref"]
    assert out["plan_ref"] and out["plan_approved"] is True
    assert len(get_task_store().list("o", "proj-1")) == 4
    # Handoff points at Construction.
    assert out["handoff"]["next_phase"] == "Construction / Build"


def test_human_path_pauses_at_first_gate_inside_nested_subgraph():
    g = build_brainstorm().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "human"}}

    # Socratic discovery: three rounds then the Discover gate — all inside the
    # nested `discover` subgraph, surfaced through the parent.
    g.invoke(_initial(interaction_mode="socratic"), cfg)
    snap = g.get_state(cfg)
    assert snap.next  # paused somewhere inside the discover subgraph
    assert snap.tasks[0].interrupts[0].value["kind"] == "user_input_required"

    g.invoke(Command(resume={"answers": ["a", "b", "c", "d"]}), cfg)
    g.invoke(Command(resume={"answers": ["a", "b", "c"]}), cfg)
    g.invoke(Command(resume={"answers": ["a", "b"]}), cfg)
    gate = g.get_state(cfg).tasks[0].interrupts[0].value
    assert gate["kind"] == "approval"
    assert gate["gate"] == "discover_summary"
