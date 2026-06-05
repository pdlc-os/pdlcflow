"""/override utility node — Tier-1 safety override (human-only, double-RED).

Upstream: skills/override + docs/pdlc/reference safety/override. A Tier-1
override bypasses a hard safety block and therefore demands an explicit
human double-RED confirmation. The node interrupts for "RED RED" and only
confirms on an exact (case-insensitive) match.

Night-shift is autonomous, and an override is human-only: under
`night_shift_active` the node MUST NOT interrupt — it refuses outright,
records an unconfirmed entry, and notes the refusal.
"""

from __future__ import annotations

from datetime import date as _date

from langgraph.types import interrupt

from ...instrumentation import instrumented_node
from ...state import PDLCState

CONFIRM_PHRASE = "RED RED"


@instrumented_node("skill.invoked")
def override_node(state: PDLCState) -> dict:
    """Confirm (or refuse) a Tier-1 override; append to the override audit log."""
    args = state.get("utility_args") or {}
    reason = args.get("reason")
    today = _date.today().isoformat()
    log = list(state.get("override_log") or [])

    # Night-shift: override is human-only — refuse without interrupting.
    if state.get("night_shift_active"):
        log.append({"reason": reason, "confirmed": False, "date": today})
        return {
            "override_log": log,
            "utility_result": {"command": "override", "refused": "night-shift"},
        }

    answer = interrupt(
        {
            "kind": "user_input_required",
            "mode": "override_confirm",
            "questions": ["Type RED RED to confirm the Tier-1 override"],
            "reason": reason,
        }
    )

    # The resume value may be the raw answer string or a dict carrying it.
    # The engine resolve endpoint sends {"answers": [...]} for question rounds.
    if isinstance(answer, dict):
        answers = answer.get("answers")
        answer = (
            answer.get("answer")
            or answer.get("response")
            or (answers[0] if isinstance(answers, list) and answers else "")
            or ""
        )
    confirmed = str(answer).strip().casefold() == CONFIRM_PHRASE.casefold()

    log.append({"reason": reason, "confirmed": confirmed, "date": today})
    return {
        "override_log": log,
        "utility_result": {
            "command": "override",
            "confirmed": confirmed,
            "outcome": "confirmed" if confirmed else "cancelled",
        },
    }
