"""/compact utility node — distills the working log to free up context."""

from __future__ import annotations

from pdlc_graph.graphs.utility import UTILITY_NODES
from pdlc_graph.graphs.utility.compact import compact_node
from pdlc_graph.llm_port import reset_completion_backend


def test_compact_is_registered():
    assert UTILITY_NODES["compact"] is compact_node


def test_compact_distills_and_shrinks_log():
    reset_completion_backend()  # deterministic stub
    state = {"project_id": "proj", "brainstorm_log": [
        {"section": "Discovery", "body": "a" * 500, "step": "s1"},
        {"section": "Design", "body": "b" * 500, "step": "s2"},
    ]}
    patch = compact_node(state)
    assert patch["utility_result"]["compacted"] is True
    assert patch["utility_result"]["entries_before"] == 2
    assert len(patch["brainstorm_log"]) == 1
    assert patch["brainstorm_log"][0]["step"] == "compact"
    assert patch["utility_result"]["compacted_ref"].startswith(("memory://", "file://", "s3://"))


def test_compact_noop_on_empty_log():
    patch = compact_node({"project_id": "p", "brainstorm_log": []})
    assert patch["utility_result"]["compacted"] is False
