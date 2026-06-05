"""Scan an upstream pdlc project — produce a Manifest."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Manifest:
    project_root: Path
    memory_files: list[Path] = field(default_factory=list)
    episodes: list[Path] = field(default_factory=list)
    bd_count: int = 0
    deployments_present: bool = False
    night_shift_state_present: bool = False

    @property
    def summary(self) -> dict[str, int]:
        return {
            "memory_files": len(self.memory_files),
            "episodes": len(self.episodes),
            "bd_tasks": self.bd_count,
            "deployments": 1 if self.deployments_present else 0,
            "night_shift_runs": 1 if self.night_shift_state_present else 0,
        }


def scan_project(root: Path) -> Manifest:
    mem_dir = root / "docs" / "pdlc" / "memory"
    m = Manifest(project_root=root)
    if not mem_dir.exists():
        return m

    for name in ("CONSTITUTION.md", "STATE.md", "INTENT.md", "ROADMAP.md",
                 "DECISIONS.md", "METRICS.md", "OVERVIEW.md", "CHANGELOG.md"):
        p = mem_dir / name
        if p.exists():
            m.memory_files.append(p)

    if (mem_dir / "DEPLOYMENTS.md").exists():
        m.deployments_present = True
        m.memory_files.append(mem_dir / "DEPLOYMENTS.md")
    if (mem_dir / "pdlc-night-shift.json").exists():
        m.night_shift_state_present = True

    episodes_dir = mem_dir / "episodes"
    if episodes_dir.exists():
        m.episodes = sorted(episodes_dir.glob("*.md"))

    # Beads count — best-effort; bd CLI is optional in pdlcflow once Postgres
    # tasks table is the source of truth.
    bd_db = root / ".beads" / "tasks.json"
    if bd_db.exists():
        import json
        try:
            data = json.loads(bd_db.read_text())
            m.bd_count = len(data.get("tasks", []))
        except Exception:
            m.bd_count = 0

    return m
