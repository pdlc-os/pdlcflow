"""Visual companion specs — structured, render-agnostic "screens".

pdlcflow replaces the upstream localhost:7352 mockup server with a panel inside
Studio (same browser as the chat). Instead of writing HTML fragments to a
screen_dir, a brainstorm node attaches a `visual` spec to the `interrupt()`
payload; it rides the existing gate store → `pending.payload.visual` → WS frame,
and the React `BrainstormVisualCompanion` draws it beside the question.

A spec is `{"screens": [screen, ...]}`. Screen types (mirroring the upstream
companion's vocabulary, minus the server):

- options : A/B/C selectable cards — clicking one answers that question.
- mermaid : a mermaid diagram (e.g. the Plan dependency tree).
- mockup  : a titled wireframe / preview block (markdown body).

All builders are pure; no I/O.
"""

from __future__ import annotations

_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def options_screen(
    title: str, options: list[dict], *, subtitle: str = "", key: str | None = None
) -> dict:
    """An A/B/C choice screen. `options` items: {"title","description"}.

    `key` ties the screen to a question (so a click maps to that answer slot);
    each option is auto-lettered a, b, c, …
    """
    lettered = [
        {
            "choice": _LETTERS[i] if i < len(_LETTERS) else str(i),
            "title": o.get("title", ""),
            "description": o.get("description", ""),
        }
        for i, o in enumerate(options)
    ]
    return {"type": "options", "key": key, "title": title, "subtitle": subtitle, "options": lettered}


def mermaid_screen(title: str, mermaid: str, *, subtitle: str = "") -> dict:
    """A mermaid-diagram screen (dependency trees, flows, architecture)."""
    return {"type": "mermaid", "title": title, "subtitle": subtitle, "mermaid": mermaid}


def mockup_screen(title: str, body: str, *, subtitle: str = "") -> dict:
    """A titled wireframe/preview block; `body` is markdown the panel renders."""
    return {"type": "mockup", "title": title, "subtitle": subtitle, "body": body}


def visual(screens: list[dict]) -> dict:
    """Wrap screens into a companion spec for an interrupt payload."""
    return {"screens": screens}
