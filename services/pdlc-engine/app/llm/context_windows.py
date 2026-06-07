"""Model → context-window size (tokens). Used by the Studio context meter to
show how close an agent's prompts came to the active model's limit. Ballpark
public values as of 2026-06; unknown models fall back to a conservative default.
"""

from __future__ import annotations

DEFAULT_CONTEXT_WINDOW = 200_000

CONTEXT_WINDOWS: dict[str, int] = {
    # Claude (direct + Bedrock ids + Vertex + CLI aliases)
    "claude-opus-4-8": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
    "anthropic.claude-opus-4-8": 200_000,
    "anthropic.claude-sonnet-4-6": 200_000,
    "anthropic.claude-haiku-4-5": 200_000,
    "opus": 200_000,
    "sonnet": 200_000,
    "haiku": 200_000,
    # OpenAI / Azure
    "gpt-5.5": 400_000,
    "gpt-5.4": 400_000,
    "gpt-5.4-mini": 400_000,
    # Gemini
    "gemini-3.1-pro": 2_000_000,
    "gemini-3.5-flash": 1_000_000,
    "gemini-3.1-flash-lite": 1_000_000,
    # Ollama (local; conservative)
    "llama3.3:70b": 128_000,
    "qwen2.5:32b": 128_000,
    "qwen2.5:7b": 128_000,
}


def context_window_for(model_id: str | None) -> int:
    if not model_id:
        return DEFAULT_CONTEXT_WINDOW
    return CONTEXT_WINDOWS.get(model_id, DEFAULT_CONTEXT_WINDOW)
