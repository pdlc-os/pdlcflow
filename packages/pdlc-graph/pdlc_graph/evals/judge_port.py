"""Judge seam — LLM-as-judge, with a deterministic offline stub.

Mirrors `pdlc_graph.llm_port`: graph/eval code calls `judge(...)` here, and the
engine injects a factory-backed judge at boot (a strong model at the configured
judge tier). Until injected — and in all hermetic tests/CI — a deterministic
`_StubJudge` answers, so the eval harness runs end-to-end with no network and no
credentials. The stub's score is a stable, explainable function of the output +
sources, so threshold/blocking logic is testable without a real model.

A judge returns a structured verdict `{"score": float 0..1, "rationale": str}`.
"""

from __future__ import annotations

import re
from typing import Protocol, TypedDict


class JudgeVerdict(TypedDict):
    score: float
    rationale: str


class _JudgeBackend(Protocol):
    def judge(
        self, *, rubric: str, dimension: str, output: str, sources: dict[str, str], tier: str | None
    ) -> JudgeVerdict: ...


_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class _StubJudge:
    """Deterministic stand-in for a real LLM judge.

    Heuristics (no network): empty output scores 0; otherwise a base score plus
    a grounding bonus for the fraction of *source* vocabulary the output reuses.
    This is intentionally crude — it is NOT a real quality signal — but it is
    stable and monotonic, which is what the harness wiring + tests need. Real
    judging requires the factory-backed judge (PDLC_RUN_EVALS + a wired model).
    """

    def judge(
        self, *, rubric: str, dimension: str, output: str, sources: dict[str, str], tier: str | None = None
    ) -> JudgeVerdict:
        out = (output or "").strip()
        if not out:
            return {"score": 0.0, "rationale": "stub: empty output"}
        ow = _words(out)
        src_words: set[str] = set()
        for s in sources.values():
            src_words |= _words(s)
        if src_words:
            overlap = len(ow & src_words) / max(1, len(src_words))
            score = 0.4 + 0.6 * min(1.0, overlap)
            why = f"stub: {dimension} grounding overlap={overlap:.2f} over {len(sources)} source(s)"
        else:
            # No sources to ground against (e.g. pure quality rubric): reward a
            # non-trivial, structured answer up to a ceiling.
            score = min(0.85, 0.5 + min(0.35, len(ow) / 200.0))
            why = f"stub: {dimension} length-heuristic words={len(ow)}"
        return {"score": round(score, 4), "rationale": why}


_backend: _JudgeBackend = _StubJudge()


def set_judge_backend(backend: _JudgeBackend) -> None:
    global _backend
    _backend = backend


def reset_judge_backend() -> None:
    global _backend
    _backend = _StubJudge()


def is_stubbed() -> bool:
    return isinstance(_backend, _StubJudge)


def judge(
    *, rubric: str, dimension: str, output: str, sources: dict[str, str] | None = None, tier: str | None = None
) -> JudgeVerdict:
    return _backend.judge(rubric=rubric, dimension=dimension, output=output, sources=sources or {}, tier=tier)
