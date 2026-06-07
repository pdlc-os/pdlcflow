"""/compact utility node — distill the accumulated brainstorm log into a concise,
fact-lossless summary so downstream node prompts stay within the model's context
window (the pdlcflow analogue of Claude Code's compaction).

The verbose log is replaced by a single "Compacted Summary" entry; the full
summary is also written to an artifact so nothing is lost. Atlas does the distill
via the LLM port (deterministic stub when the LLM is unwired).
"""

from __future__ import annotations

from ...instrumentation import instrumented_node
from ...llm_port import complete
from ...ports import put_artifact
from ...state import PDLCState

_SYSTEM = (
    "You compact a project's working log. Produce a concise summary that is "
    "LOSSLESS on facts — preserve every decision, requirement, constraint, and "
    "open question — while dropping verbosity and repetition. No preamble."
)


def _log_text(brainstorm_log: list[dict]) -> str:
    return "\n\n".join(
        f"### {e.get('section', '')} ({e.get('step', '')})\n{e.get('body', '')}"
        for e in brainstorm_log
    )


@instrumented_node("skill.invoked")
def compact_node(state: PDLCState) -> dict:
    log = state.get("brainstorm_log") or []
    if not log:
        return {"utility_result": {"command": "compact", "compacted": False,
                                   "reason": "nothing to compact"}}

    summary = complete("atlas", _log_text(log), system=_SYSTEM).strip()
    project_id = state.get("project_id") or "proj"
    ref = put_artifact(project_id, "docs/pdlc/memory/COMPACTED.md", summary)

    return {
        # Replace the verbose log with one compacted entry (full text kept in the artifact).
        "brainstorm_log": [{"section": "Compacted Summary", "body": summary, "step": "compact"}],
        "utility_result": {
            "command": "compact",
            "compacted": True,
            "entries_before": len(log),
            "entries_after": 1,
            "compacted_ref": ref,
        },
    }
