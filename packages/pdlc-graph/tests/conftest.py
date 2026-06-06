"""Reset global eval + instrumentation state between tests so an eval test that
enables the harness can't leak into the rest of the suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_eval_state():
    from pdlc_graph.evals import reset_eval_config, reset_judge_backend

    reset_eval_config()
    reset_judge_backend()
    yield
    reset_eval_config()
    reset_judge_backend()
