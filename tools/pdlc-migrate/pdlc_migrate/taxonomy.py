"""Interactive taxonomy assignment.

Prompts for initiative / application / domains for a migrated project. The
Atlas Console has the same wizard for ongoing assignments — this CLI version
is just for the bulk-import path.
"""

from __future__ import annotations

from pathlib import Path


def assign_taxonomy(_project_root: Path, _engine_url: str) -> None:
    """Phase A stub — real impl uses Typer prompts + engine API."""
    print("[taxonomy] interactive assignment lands in Phase I")
