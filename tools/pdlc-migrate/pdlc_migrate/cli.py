"""Migration CLI entry — typer subcommands.

scan      — read source pdlc project's docs/pdlc/memory/, list files, count
            episodes + bd tasks. Outputs a manifest the user reviews.
push      — POST the project's memory files + parsed entity rows to the engine
            (/v1/migrate/import). Preserves bd-NN external ids.
taxonomy  — interactive: assign migrated project to initiative + application
            + domains.
backfill  — synthesize historical events from the phase history + decision log
            and push them tagged synthetic=true so dashboards are non-empty on
            day one. Idempotent (the engine dedups on event_id).
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .backfill import backfill_events
from .push import build_import_payload, push_payload
from .scan import scan_project
from .taxonomy import assign_taxonomy

app = typer.Typer(help="Migrate an upstream pdlc project into pdlcflow.")
console = Console()

_OrgOpt = typer.Option(..., envvar="PDLC_ORG_ID", help="Target org id (uuid).")
_ProjOpt = typer.Option(..., envvar="PDLC_PROJECT_ID", help="Target project id (uuid).")
_EngineOpt = typer.Option(..., envvar="PDLC_ENGINE_URL", help="Engine base URL.")


@app.command()
def scan(project_root: Path) -> None:
    """Inspect an upstream pdlc project's memory + Beads + deployments."""
    manifest = scan_project(project_root)
    table = Table(title=f"scan: {project_root}")
    table.add_column("kind")
    table.add_column("count")
    for k, v in manifest.summary.items():
        table.add_row(k, str(v))
    console.print(table)


@app.command()
def push(
    project_root: Path,
    engine_url: str = _EngineOpt,
    org_id: str = _OrgOpt,
    project_id: str = _ProjOpt,
) -> None:
    """Push memory files + parsed entity rows to the engine."""
    payload = build_import_payload(
        project_root,
        org_id=org_id,
        project_id=project_id,
        taxonomy={"initiative": None, "application": None, "domains": []},
        events=[],
    )
    result = push_payload(payload, engine_url)
    console.print(f"[green]pushed[/] {result}")


@app.command()
def taxonomy(project_root: Path, engine_url: str = _EngineOpt) -> None:
    """Interactive — assign initiative / application / domains."""
    assign_taxonomy(project_root, engine_url)


@app.command()
def backfill(
    project_root: Path,
    engine_url: str = _EngineOpt,
    org_id: str = _OrgOpt,
    project_id: str = _ProjOpt,
) -> None:
    """Synthesize + push historical events (synthetic=true, idempotent)."""
    events = backfill_events(project_root)
    payload = {
        "org_id": str(org_id),
        "project_id": str(project_id),
        "taxonomy": {"initiative": None, "application": None, "domains": []},
        "memory_files": [],
        "tasks": [],
        "decisions": [],
        "deployments": [],
        "events": events,
    }
    result = push_payload(payload, engine_url)
    console.print(f"[green]backfilled[/] {result.get('events', len(events))} synthetic events")


if __name__ == "__main__":
    app()
