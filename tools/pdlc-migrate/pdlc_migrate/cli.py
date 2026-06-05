"""Migration CLI entry — typer subcommands.

scan      — read source pdlc project's docs/pdlc/memory/, list files, count
            episodes + bd tasks. Outputs a manifest the user reviews.
push      — POST manifest to pdlc-engine endpoints; create memory_files,
            tasks, decisions, episodes, deployments rows. Preserves bd-NN.
taxonomy  — interactive: assign migrated project to initiative + application
            + domains.
backfill  — synthesize historical events from episodes + decision log + phase
            history; events tagged synthetic=true so dashboards distinguish.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .scan import scan_project
from .push import push_manifest
from .backfill import backfill_events
from .taxonomy import assign_taxonomy

app = typer.Typer(help="Migrate an upstream pdlc project into pdlcflow.")
console = Console()


@app.command()
def scan(project_root: Path) -> None:
    """Inspect an upstream pdlc project's memory + Beads + deployments."""
    manifest = scan_project(project_root)
    table = Table(title=f"scan: {project_root}")
    table.add_column("kind"); table.add_column("count")
    for k, v in manifest.summary.items():
        table.add_row(k, str(v))
    console.print(table)


@app.command()
def push(project_root: Path, engine_url: str = typer.Option(..., envvar="PDLC_ENGINE_URL")) -> None:
    """Push manifest contents to the engine."""
    manifest = scan_project(project_root)
    result = push_manifest(manifest, engine_url)
    console.print(f"[green]pushed[/] {result}")


@app.command()
def taxonomy(project_root: Path, engine_url: str = typer.Option(..., envvar="PDLC_ENGINE_URL")) -> None:
    """Interactive — assign initiative / application / domains."""
    assign_taxonomy(project_root, engine_url)


@app.command()
def backfill(project_root: Path, engine_url: str = typer.Option(..., envvar="PDLC_ENGINE_URL")) -> None:
    """Synthesize historical events from episodes + decisions + phase history."""
    n = backfill_events(project_root, engine_url)
    console.print(f"[green]backfilled[/] {n} synthetic events")


if __name__ == "__main__":
    app()
