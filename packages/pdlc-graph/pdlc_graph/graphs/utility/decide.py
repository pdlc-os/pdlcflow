"""/decide utility node — record a decision in the PDLC Decision Registry.

Upstream: skills/decide. Bounded + hermetic port. Reads
`utility_args` {"title", "rationale"}; if the rationale is missing Atlas drafts
one via the LLM port. Appends a new {id, title, rationale, date} entry to the
append-only `decisions` list, re-renders DECISIONS.md, and persists it to
`decisions_ref`.
"""

from __future__ import annotations

from datetime import date as _date

from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...ports import put_artifact
from ...render import render_decisions
from ...state import PDLCState


@instrumented_node("skill.invoked")
def decide_node(state: PDLCState) -> dict:
    """Record a decision and re-render the Decision Registry."""
    args = state.get("utility_args") or {}
    title = (args.get("title") or "Untitled decision").strip()
    rationale = (args.get("rationale") or "").strip()

    if not rationale:
        rationale = complete(
            "atlas",
            f"Draft a one-paragraph rationale for the decision titled "
            f"'{title}'. Be concrete about the problem it solves.",
            system="PDLC decision recorder",
        ).strip()

    decisions = list(state.get("decisions") or [])
    next_n = len(decisions) + 1
    entry = {
        "id": f"D-{next_n}",
        "title": title,
        "rationale": rationale,
        "date": _date.today().isoformat(),
    }
    decisions.append(entry)

    project_id = state.get("project_id") or "proj"
    decisions_md = render_decisions(decisions)
    decisions_ref = put_artifact(project_id, "docs/pdlc/memory/DECISIONS.md", decisions_md)

    return {
        "decisions": decisions,
        "decisions_ref": decisions_ref,
        "utility_result": {
            "command": "decide",
            "id": entry["id"],
            "title": title,
            "count": len(decisions),
        },
    }
