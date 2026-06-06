"""Rubric text for the LLM-as-judge evals.

These are the prompts a real judge model scores against. The deterministic stub
ignores the prose (it uses heuristics), but the real factory-backed judge uses
them verbatim, so keep them concrete and scorable on a 0-1 scale.
"""

from __future__ import annotations

# Per-agent output-quality rubrics, keyed by the persona's role focus. A judge
# scores how well the produced artifact meets this bar (0 = unusable, 1 = ships).
AGENT_QUALITY_RUBRICS: dict[str, str] = {
    "atlas": "Score this PRD/spec: clear problem statement, measurable success criteria, "
             "explicit scope/non-goals, testable acceptance criteria, no hand-waving.",
    "neo": "Score this design/architecture: sound decomposition, named trade-offs, "
           "addresses the requirements, no unjustified complexity, considers failure modes.",
    "bolt": "Score this backend plan/output: correct data model + API contract, error handling, "
            "idempotency/consistency considered, testable.",
    "friday": "Score this frontend plan/output: component structure, state management, "
              "accessibility, matches the UX intent.",
    "muse": "Score this UX: clear user flow, addresses the user's job-to-be-done, "
            "no dark patterns, consistent with design laws.",
    "pulse": "Score this DevOps/deploy plan: environment correctness, rollback path, "
             "observability, no production-safety violations.",
    "echo": "Score this QA/test plan: coverage of the acceptance criteria, edge cases, "
            "negative paths, deterministic and meaningful assertions.",
    "phantom": "Score this security review: realistic threat coverage, severity-rated findings, "
               "concrete remediations, no false alarms.",
    "jarvis": "Score this documentation: accurate, complete for the audience, no drift from "
              "the implementation, navigable.",
    "_default": "Score this output for clarity, correctness, completeness, and fitness for purpose.",
}

GROUNDEDNESS_RUBRIC = (
    "Score how well EVERY claim in the output is supported by the provided SOURCES. "
    "1.0 = every claim is traceable to a source; 0.0 = the output invents facts not in any source "
    "(hallucination). Penalize unsupported specifics (numbers, names, decisions) heavily."
)

FAITHFULNESS_RUBRIC = (
    "Score whether the output faithfully represents the sources without distortion, omission of "
    "material caveats, or overstatement. 1.0 = faithful; 0.0 = misrepresents the sources."
)


def agent_quality_rubric(persona: str) -> str:
    return AGENT_QUALITY_RUBRICS.get(persona, AGENT_QUALITY_RUBRICS["_default"])
