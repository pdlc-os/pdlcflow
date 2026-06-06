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

Live token streaming: when the engine has set a token publisher AND a thread
context is active (the GraphRunner sets it around each turn), `complete()`
streams the backend's output and publishes `token` frames to the thread's
WebSocket channel — powering the Studio's live "drafting" preview. Disabled by
default (no publisher set) so tests + the no-stream path are byte-identical.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from typing import Protocol

# The thread the current turn belongs to (set by the runner); token frames route
# to `thread:{id}`. None outside a turn → no streaming.
_current_thread: ContextVar[str | None] = ContextVar("pdlc_current_thread", default=None)

# Publisher(thread_id, frame) injected by the engine to push frames onto the bus.
_token_publisher: Callable[[str, dict], None] | None = None


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

    def stream(
        self, persona: str, prompt: str, *, tier: str | None = None, system: str | None = None
    ) -> Iterator[str]:
        # Chunk the deterministic completion word-by-word so streaming is visible
        # (and testable) without a real model.
        text = self.complete(persona, prompt, tier=tier, system=system)
        for word in text.split(" "):
            yield word + " "


_backend: _CompletionBackend = _StubBackend()


def set_completion_backend(backend: _CompletionBackend) -> None:
    """Engine boot calls this with a factory-backed implementation."""
    global _backend
    _backend = backend


def reset_completion_backend() -> None:
    """Restore the offline stub (used by tests)."""
    global _backend
    _backend = _StubBackend()


# ---- token streaming seam (engine wires the publisher; runner sets the thread) ----
def set_token_publisher(fn: Callable[[str, dict], None] | None) -> None:
    global _token_publisher
    _token_publisher = fn


def reset_token_publisher() -> None:
    global _token_publisher
    _token_publisher = None


def set_thread_context(thread_id: str | None):
    """Bind the current turn's thread id; returns a token for `reset_thread_context`."""
    return _current_thread.set(thread_id)


def reset_thread_context(token) -> None:
    _current_thread.reset(token)


def complete(
    persona: str, prompt: str, *, tier: str | None = None, system: str | None = None
) -> str:
    """Run a single completion as `persona`. Returns the model's text.

    Streams `token` frames to the thread channel when a publisher + thread
    context are active and the backend supports streaming; otherwise a plain
    blocking completion (identical output)."""
    thread = _current_thread.get()
    pub = _token_publisher
    if pub is not None and thread and hasattr(_backend, "stream"):
        pub(thread, {"type": "token", "thread_id": thread, "start": True, "persona": persona})
        chunks: list[str] = []
        try:
            for ch in _backend.stream(persona, prompt, tier=tier, system=system):  # type: ignore[attr-defined]
                chunks.append(ch)
                pub(thread, {"type": "token", "thread_id": thread, "chunk": ch})
            pub(thread, {"type": "token", "thread_id": thread, "done": True})
            return "".join(chunks)
        except Exception:
            # streaming failed mid-way — fall back to a full completion
            pub(thread, {"type": "token", "thread_id": thread, "done": True})
            return _backend.complete(persona, prompt, tier=tier, system=system)
    return _backend.complete(persona, prompt, tier=tier, system=system)


def is_stubbed() -> bool:
    return isinstance(_backend, _StubBackend)
