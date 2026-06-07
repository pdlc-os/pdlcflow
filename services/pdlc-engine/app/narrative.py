"""Work-narrative generator.

Turns a clickstream work summary (from the analytics store) into a readable,
standup-style narrative that separates human work (via the Studio) from
autonomous agent work, for the Nexus Console. Generation goes through the
pdlc-graph LLM port, so it uses the deterministic offline stub when the LLM is
unwired (hermetic dev/CI) and a real model when `PDLC_WIRE_LLM` is on. The
caller binds the tenant (set_current_org) so the org's provider/tier apply.
"""

from __future__ import annotations

import json

from pdlc_graph.llm_port import complete

_SYSTEM = (
    "You are a delivery lead writing a concise, factual narrative of the work a "
    "software team completed in a time window. Clearly separate what HUMANS did "
    "(via the Studio: resolving approval gates, recording decisions, overrides) "
    "from what AGENTS did autonomously (design, build, review, party meetings, "
    "night-shift runs). Call out milestones (gates resolved, deploys, phase "
    "transitions, test failures, night-shift verdicts) and end with a one-line "
    "bottom line. Ground every statement ONLY in the provided stats — never "
    "invent specifics, names, or numbers that aren't present."
)

# Persona whose tier/voice drives the narrative (Atlas = product/delivery lead).
_NARRATOR = "atlas"


def build_narrative(summary: dict) -> str:
    """Generate the narrative text for a work summary dict."""
    window = summary.get("window", {})
    prompt = (
        f"Window: {window.get('from') or 'beginning'} → {window.get('to') or 'now'}.\n"
        f"Work summary (JSON):\n{json.dumps(summary, default=str)[:6000]}\n\n"
        "Write the narrative now."
    )
    return complete(_NARRATOR, prompt, system=_SYSTEM).strip()
