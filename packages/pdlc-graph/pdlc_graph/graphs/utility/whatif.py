"""/whatif utility node — read-only hypothetical scenario analysis.

Upstream: skills/whatif. STRICTLY read-only: it MUST NOT mutate paused,
abandoned, decisions, roadmap_claim, or any other project state. Reads
`utility_args["scenario"]`, has Neo analyze it via the LLM port, renders the
analysis to an artifact, and returns only `whatif_ref` + `utility_result`.
"""

from __future__ import annotations

from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...ports import put_artifact
from ...state import PDLCState


def _slug(text: str) -> str:
    words = text.strip().lower().split()[:5]
    slug = "-".join(words)[:30].strip("-")
    return slug or "scenario"


@instrumented_node("skill.invoked")
def whatif_node(state: PDLCState) -> dict:
    """Analyze a hypothetical scenario without mutating project state."""
    args = state.get("utility_args") or {}
    scenario = (args.get("scenario") or "").strip() or "(no scenario provided)"

    analysis = complete(
        "neo",
        f"Read-only what-if analysis. Assess the implications of this scenario "
        f"on architecture, scope, effort, and risk. Do not recommend mutating "
        f"any state.\n\nSCENARIO: {scenario}",
        system="PDLC what-if analyst (read-only)",
    ).strip()

    body = (
        f"# What-If Analysis\n\n"
        f"**Scenario:** {scenario}\n"
        f"**Status:** Exploratory (read-only)\n\n"
        f"## Analysis\n\n{analysis}\n"
    )

    project_id = state.get("project_id") or "proj"
    whatif_ref = put_artifact(
        project_id, f"docs/pdlc/mom/MOM_whatif_{_slug(scenario)}.md", body
    )

    # READ-ONLY: return only the artifact ref + summary; never touch
    # paused/abandoned/decisions/roadmap_claim.
    return {
        "whatif_ref": whatif_ref,
        "utility_result": {
            "command": "whatif",
            "scenario": scenario,
            "read_only": True,
        },
    }
