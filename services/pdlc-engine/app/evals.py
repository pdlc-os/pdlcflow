"""Eval wiring — turn the harness on and install the factory-backed judge.

pdlc-graph ships the eval framework + a deterministic stub judge. At boot the
engine: (1) sets the enabled flag + blocking overrides from settings, and
(2) installs an LLM-as-judge backed by the provider factory at the judge tier —
but ONLY when both `run_evals` and `wire_llm` are set (so CI/dev stay hermetic
on the deterministic stub). Wiring never blocks boot.
"""

from __future__ import annotations

import json
import logging
import re

log = logging.getLogger("pdlc.evals")

_NUM = re.compile(r"([01](?:\.\d+)?)")


class FactoryJudgeBackend:
    """LLM-as-judge over the provider factory. Asks the model for a JSON verdict
    {"score": 0..1, "rationale": str}; parses defensively."""

    def __init__(self, factory, org_id: str, tier: str) -> None:
        self._factory = factory
        self._org_id = org_id
        self._tier = tier

    def judge(self, *, rubric: str, dimension: str, output: str, sources: dict, tier=None):
        from .llm.factory import TenantCtx  # type: ignore

        model = self._factory.get_model(
            persona="phantom",  # a skeptical reviewer persona for judging
            tier=tier or self._tier,  # type: ignore[arg-type]
            tenant=TenantCtx(org_id=self._org_id),
        )
        src = "\n\n".join(f"### SOURCE: {k}\n{v}" for k, v in (sources or {}).items()) or "(none)"
        prompt = (
            f"You are a strict evaluator scoring the {dimension} of an agent's output.\n"
            f"RUBRIC:\n{rubric}\n\nSOURCES:\n{src}\n\nOUTPUT TO SCORE:\n{output}\n\n"
            'Respond with ONLY JSON: {"score": <float 0.0-1.0>, "rationale": "<one sentence>"}.'
        )
        try:
            result = model.invoke([("human", prompt)])
            text = getattr(result, "content", str(result))
            return self._parse(text)
        except Exception as exc:  # never raise into the eval runner
            log.warning("judge model failed (%s); neutral score", exc)
            return {"score": 0.5, "rationale": f"judge error: {exc}"}

    @staticmethod
    def _parse(text: str) -> dict:
        try:
            obj = json.loads(text[text.index("{"): text.rindex("}") + 1])
            score = float(obj.get("score"))
            return {"score": max(0.0, min(1.0, score)), "rationale": str(obj.get("rationale", ""))[:300]}
        except Exception:
            m = _NUM.search(text or "")
            return {"score": float(m.group(1)) if m else 0.5, "rationale": (text or "")[:200]}


def wire_evals(settings) -> bool:
    """Enable the harness + (optionally) install the factory-backed judge.

    Returns True if evals are enabled. Always safe to call.
    """
    from pdlc_graph.evals import set_blocking_overrides, set_evals_enabled

    enabled = bool(getattr(settings, "run_evals", False))
    set_evals_enabled(enabled)
    blocking = [s.strip() for s in (getattr(settings, "eval_blocking", "") or "").split(",") if s.strip()]
    set_blocking_overrides(blocking)
    if not enabled:
        return False

    if getattr(settings, "wire_llm", False):
        try:
            from pdlc_graph.evals import set_judge_backend

            from .llm.factory import LLMProviderFactory

            set_judge_backend(
                FactoryJudgeBackend(
                    LLMProviderFactory(), org_id="self-host",
                    tier=getattr(settings, "judge_tier", "opus"),
                )
            )
            log.info("evals enabled with factory-backed judge (tier=%s)", settings.judge_tier)
        except Exception as exc:  # fall back to the deterministic stub judge
            log.warning("judge wiring failed (%s); using deterministic stub judge", exc)
    else:
        log.info("evals enabled with deterministic stub judge (wire_llm off)")
    return True
