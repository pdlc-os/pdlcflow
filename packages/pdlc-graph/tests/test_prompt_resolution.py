"""Persona prompt resolution seam (PRD-10 M0).

The soul-spec finally reaches models: complete() always carries the persona's
effective system prompt (org override via the injected resolver, else the
packaged spec), with caller `system` appended as a task role. The offline stub
hashes (persona, prompt) only, so all pre-M0 outputs stay byte-identical.
"""

from __future__ import annotations

import pytest
from pdlc_graph.llm_port import (
    complete,
    reset_completion_backend,
    set_completion_backend,
)
from pdlc_graph.personas import (
    load_persona_spec,
    reset_prompt_resolver,
    resolve_persona_prompt,
    set_prompt_resolver,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_prompt_resolver()
    reset_completion_backend()
    yield
    reset_prompt_resolver()
    reset_completion_backend()


def test_resolver_defaults_to_packaged_spec():
    assert resolve_persona_prompt("muse") == load_persona_spec("muse")


def test_injected_resolver_wins_and_none_falls_back():
    set_prompt_resolver(lambda p: "org-tuned muse" if p == "muse" else None)
    assert resolve_persona_prompt("muse") == "org-tuned muse"
    assert resolve_persona_prompt("neo") == load_persona_spec("neo")


def test_resolver_errors_never_break_resolution():
    def boom(_p):
        raise RuntimeError("db down")
    set_prompt_resolver(boom)
    assert resolve_persona_prompt("muse") == load_persona_spec("muse")


class _SpyBackend:
    def __init__(self):
        self.calls: list[dict] = []

    def complete(self, persona, prompt, *, tier=None, system=None):
        self.calls.append({"persona": persona, "system": system})
        return "ok"


def test_complete_injects_persona_spec_as_system():
    spy = _SpyBackend()
    set_completion_backend(spy)
    complete("muse", "brainstorm a feature")
    assert spy.calls[0]["system"] == load_persona_spec("muse")


def test_caller_system_becomes_task_role_suffix():
    spy = _SpyBackend()
    set_completion_backend(spy)
    complete("neo", "plan it", system="PDLC PRD author")
    sys = spy.calls[0]["system"]
    assert sys.startswith(load_persona_spec("neo"))
    assert sys.endswith("## Task role\nPDLC PRD author")


def test_org_override_flows_into_complete():
    set_prompt_resolver(lambda p: "fintech-tuned atlas")
    spy = _SpyBackend()
    set_completion_backend(spy)
    complete("atlas", "review this", system="reviewer")
    assert spy.calls[0]["system"] == "fintech-tuned atlas\n\n## Task role\nreviewer"


def test_unknown_persona_leaves_system_untouched():
    spy = _SpyBackend()
    set_completion_backend(spy)
    complete("not-a-persona", "x", tier="premium", system="raw")
    assert spy.calls[0]["system"] == "raw"


def test_stub_outputs_remain_byte_identical():
    # The stub ignores `system` by design (hashes persona|prompt) — the M0
    # guarantee that hermetic CI output cannot drift.
    before = "[stub:muse:balanced:"
    out = complete("muse", "brainstorm a feature")
    assert out.startswith(before)
    set_prompt_resolver(lambda p: "totally different org prompt")
    assert complete("muse", "brainstorm a feature") == out
