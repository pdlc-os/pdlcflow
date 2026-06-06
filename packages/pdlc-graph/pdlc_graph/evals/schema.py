"""Core eval types — the context an eval sees, and the result it returns.

An eval is a pure function `(EvalContext, EvalSpec) -> EvalResult`. Results are
emitted as `eval.scored` events (and `eval.blocked` when a blocking eval fails),
so they flow into the same analytics pipeline as every other clickstream event.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalContext:
    """Everything an eval needs to judge one piece of agent output."""

    trigger: str  # the step that produced the output: prd | design_docs | plan | review | episode | sentinel_relay | regression
    target: str  # what is being evaluated: an agent persona (e.g. "atlas") or a step id
    output: str  # the produced artifact / text
    sources: dict[str, str] = field(default_factory=dict)  # name -> source text the output must be grounded in
    state: dict = field(default_factory=dict)  # graph state (for org/project/roadmap dims on the emitted event)
    extra: dict = field(default_factory=dict)  # eval-specific inputs (e.g. {"marker", "relayed"} for faithful_relay)


@dataclass
class EvalResult:
    eval_id: str
    kind: str  # "llm_judge" | "deterministic"
    dimension: str  # quality | groundedness | citation | faithful_relay | drift
    target: str
    trigger: str
    score: float  # 0.0-1.0
    threshold: float
    passed: bool
    blocking: bool
    rationale: str = ""
    refs: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "eval_id": self.eval_id,
            "kind": self.kind,
            "dimension": self.dimension,
            "target": self.target,
            "trigger": self.trigger,
            "score": round(float(self.score), 4),
            "passed": self.passed,
            "threshold": self.threshold,
            "blocking": self.blocking,
            "rationale": self.rationale[:500],
        }
