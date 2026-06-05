"""Tests for the DESIGN sub-phase (steps 9-12, gate `design_docs_approve`)."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pdlc_graph.graphs.brainstorm.design import build_design
from pdlc_graph.ports import (
    get_artifact,
    reset_artifact_store,
    reset_task_store,
)


@pytest.fixture(autouse=True)
def _hermetic():
    reset_artifact_store()
    reset_task_store()
    yield


def _intr(g, cfg):
    """Pending interrupt value (langgraph 0.2.x has no __interrupt__ key).

    Reads from `tasks[].interrupts`: a node that interrupts repeatedly in a loop
    (Bloom's rounds) leaves `.next` empty between resumes while the interrupt
    stays attached to the task.
    """
    snap = g.get_state(cfg)
    for task in snap.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    raise AssertionError("expected a pending interrupt but none was found")


def _initial(**overrides) -> dict:
    base = {
        "feature": "saved searches",
        "project_id": "proj-1",
        "interaction_mode": "socratic",
        "prd_ref": "memory://proj-1/docs/pdlc/prds/PRD_saved-searches.md",
        "brainstorm_log": [{"section": "Discover", "body": "earlier notes"}],
    }
    base.update(overrides)
    return base


def test_socratic_runs_with_blooms_rounds_and_gate():
    g = build_design().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    g.invoke(_initial(), cfg)
    # First pause: Bloom's Round 1 (Mechanics).
    intr = _intr(g, cfg)
    assert intr["kind"] == "user_input_required"
    assert "Mechanics" in (intr.get("context") or "")

    # Three Bloom's rounds, each one ask() == one resume.
    g.invoke(Command(resume={"answers": ["a1", "a2"]}), cfg)
    assert "Apply" in (_intr(g, cfg).get("context") or "")

    g.invoke(Command(resume={"answers": ["b1", "b2"]}), cfg)
    assert "Trade-offs" in (_intr(g, cfg).get("context") or "")

    g.invoke(Command(resume={"answers": ["c1", "c2"]}), cfg)
    # Next pause is the design approval gate.
    gate = _intr(g, cfg)
    assert gate["kind"] == "approval"
    assert gate["gate"] == "design_docs_approve"

    final = g.invoke(Command(resume={"approved": True}), cfg)
    assert final["design_approved"] is True

    # design_dir set, five artifact links present.
    assert final["design_dir"] == "docs/pdlc/design/saved-searches"
    docs = final["design_docs"]
    for key in ("architecture", "data_model", "api_contracts", "threat_model", "ux_review"):
        assert key in docs
    assert final["threat_model_ref"]
    assert final["ux_review_ref"]

    # Bloom's discovery recorded into the brainstorm log (preserving prior entries).
    sections = [e.get("section") for e in final["brainstorm_log"]]
    assert "Discover" in sections
    assert "Design Discovery (Bloom's Taxonomy)" in sections

    # Artifacts are real, rendered markdown with the template-version markers.
    tm = get_artifact(final["threat_model_ref"])
    assert "pdlc-template-version: 1.0.0" in tm
    ux = get_artifact(final["ux_review_ref"])
    assert "pdlc-template-version: 1.5.0" in ux
    arch = get_artifact(docs["architecture"])
    assert "# Architecture — saved searches" in arch


def test_full_triage_convenes_parties():
    # All-True signals -> full triage for both threat-model and design-laws.
    g = build_design().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "full"}}
    init = _initial(
        threat_signals=[True, True, True],
        ux_signals=[True, True, True],
    )
    g.invoke(init, cfg)
    g.invoke(Command(resume={"answers": ["a1", "a2"]}), cfg)
    g.invoke(Command(resume={"answers": ["b1", "b2"]}), cfg)
    g.invoke(Command(resume={"answers": ["c1", "c2"]}), cfg)
    final = g.invoke(Command(resume={"approved": True}), cfg)

    tm = get_artifact(final["threat_model_ref"])
    assert "**Triage:** Full" in tm
    assert "Threats Identified" in tm
    ux = get_artifact(final["ux_review_ref"])
    assert "**Triage:** Full" in ux
    assert "Findings & Proposed Actions" in ux


def test_skip_triage_produces_one_line_record():
    g = build_design().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "skip"}}
    init = _initial(
        threat_signals=[False, False, False],
        ux_signals=[False, False, False],
    )
    g.invoke(init, cfg)
    g.invoke(Command(resume={"answers": ["a1", "a2"]}), cfg)
    g.invoke(Command(resume={"answers": ["b1", "b2"]}), cfg)
    g.invoke(Command(resume={"answers": ["c1", "c2"]}), cfg)
    final = g.invoke(Command(resume={"approved": True}), cfg)

    tm = get_artifact(final["threat_model_ref"])
    assert "**Triage:** Skipped" in tm
    ux = get_artifact(final["ux_review_ref"])
    assert "**Triage:** Skipped" in ux


def test_night_shift_runs_to_completion_without_interrupt():
    g = build_design().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "ns"}}
    out = g.invoke(_initial(night_shift_active=True), cfg)
    assert "__interrupt__" not in out
    assert out["design_approved"] is True
    assert out["design_docs"]["architecture"]
    assert out["threat_model_ref"]
    assert out["ux_review_ref"]
