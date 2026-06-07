"""Subscription-CLI chat model — shells out to a locally-installed coding-agent
CLI (Claude Code / Codex / Gemini CLI) in non-interactive mode, so completions
bill against the logged-in *subscription* rather than an API key.

SINGLE-USER SELF-HOST ONLY. These are gated by `enable_cli_providers` and refused
when auth/multi-tenant is on (see the factory). The prompt is piped on **stdin**
(no shell, no arg injection); output is the CLI's stdout. Non-streaming + a
subprocess per call, so expect CLI-startup latency — fine for one local user.
"""

from __future__ import annotations

import subprocess
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.messages import BaseMessage


def render_prompt(messages: list[BaseMessage]) -> str:
    """Flatten system+human messages into one prompt string for the CLI."""
    parts: list[str] = []
    for m in messages:
        content = m.content if isinstance(m.content, str) else str(m.content)
        if content.strip():
            parts.append(content)
    return "\n\n".join(parts)


class CLIChatModel(SimpleChatModel):
    """Runs `command` with the prompt on stdin and returns stdout."""

    command: list[str]
    timeout_s: int = 300

    @property
    def _llm_type(self) -> str:
        return "pdlc-cli"

    def _call(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        prompt = render_prompt(messages)
        try:
            proc = subprocess.run(
                self.command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"CLI provider binary not found: {self.command[0]!r}. Install the CLI and "
                f"log in (subscription), or set the *_BIN path."
            ) from exc
        if proc.returncode != 0:
            raise RuntimeError(
                f"{self.command[0]} exited {proc.returncode}: {proc.stderr.strip()[:500]}"
            )
        return proc.stdout.strip()


def build_cli(binary: str, base_args: list[str], model_flag: str, model_id: str) -> CLIChatModel:
    """Assemble the argv: <binary> <base_args...> <model_flag> <model_id>."""
    command = [binary, *base_args]
    if model_flag and model_id:
        command += [model_flag, model_id]
    return CLIChatModel(command=command)
