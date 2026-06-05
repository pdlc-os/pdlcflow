"""Taxonomy assignment for a migrated project.

``assign_taxonomy_core`` is the pure, prompt-free core that the import pipeline
and the Atlas Console wizard both call. ``assign_taxonomy`` is the thin
interactive CLI wrapper (Typer prompts) used by the bulk-import path.
"""

from __future__ import annotations

from pathlib import Path

import typer

from .scan import Manifest, parse_tasks


def _derive_domains(root: Path) -> list[str]:
    """Best-effort domains from Beads ``domain:<name>`` task labels."""
    found: set[str] = set()
    for task in parse_tasks(root):
        for label in task.get("labels", []):
            if label.startswith("domain:"):
                found.add(label.split(":", 1)[1])
    return sorted(found)


def assign_taxonomy_core(
    manifest_or_root: Manifest | Path,
    *,
    initiative: str | None,
    application: str | None,
    domains: list[str] | None = None,
) -> dict:
    """Pure taxonomy assignment — no prompts, no I/O beyond optional derivation.

    Returns ``{"initiative", "application", "domains"}``. When ``domains`` is
    ``None`` the domains are derived from the project's Beads ``domain:`` task
    labels; otherwise the provided list is de-duplicated and sorted.
    """
    root = (
        manifest_or_root.project_root
        if isinstance(manifest_or_root, Manifest)
        else manifest_or_root
    )
    if domains is None:
        resolved = _derive_domains(root)
    else:
        resolved = sorted(set(domains))
    return {
        "initiative": initiative,
        "application": application,
        "domains": resolved,
    }


def assign_taxonomy(project_root: Path, engine_url: str) -> dict:
    """Interactive wrapper — prompt for taxonomy then delegate to the core."""
    initiative = typer.prompt("Initiative", default="")
    application = typer.prompt("Application", default="")
    raw_domains = typer.prompt("Domains (comma-separated)", default="")
    domains = [d.strip() for d in raw_domains.split(",") if d.strip()] or None
    return assign_taxonomy_core(
        project_root,
        initiative=initiative or None,
        application=application or None,
        domains=domains,
    )
