"""LLM port — the graph package's seam to the engine's provider factory.

The graph package must stay free of the engine's runtime deps (boto3,
langchain provider SDKs, asyncpg). So instead of importing the factory,
nodes call `complete(persona, prompt)` here. At boot the engine injects a
real backend via `set_completion_backend(...)` that resolves the persona's
tier + provider through `app.llm.LLMProviderFactory` and calls the model.

Until injected, a deterministic `_StubBackend` answers — so the whole
Inception graph runs in CI with no network, no credentials, and no model
drift. Stub output is a stable function of (persona, prompt) so tests can
assert on it.
"""

from __future__ import annotations

import hashlib
from typing import Protocol


class _CompletionBackend(Protocol):
    def complete(
        self, persona: str, prompt: str, *, tier: str | None, system: str | None
    ) -> str: ...


class _StubBackend:
    """Deterministic, offline stand-in for a real chat model."""

    def complete(
        self, persona: str, prompt: str, *, tier: str | None = None, system: str | None = None
    ) -> str:
        digest = hashlib.sha256(f"{persona}|{prompt}".encode()).hexdigest()[:8]
        head = " ".join(prompt.split()[:24])
        return f"[stub:{persona}:{tier or 'opus'}:{digest}] {head}"


_backend: _CompletionBackend = _StubBackend()


def set_completion_backend(backend: _CompletionBackend) -> None:
    """Engine boot calls this with a factory-backed implementation."""
    global _backend
    _backend = backend


def reset_completion_backend() -> None:
    """Restore the offline stub (used by tests)."""
    global _backend
    _backend = _StubBackend()


def complete(
    persona: str, prompt: str, *, tier: str | None = None, system: str | None = None
) -> str:
    """Run a single completion as `persona`. Returns the model's text."""
    return _backend.complete(persona, prompt, tier=tier, system=system)


def is_stubbed() -> bool:
    return isinstance(_backend, _StubBackend)
