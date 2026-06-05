"""Scan an upstream pdlc project — produce a Manifest + parse memory files.

The ``scan_project`` Manifest is the cheap summary (counts only). The
``parse_*`` helpers below do the real extraction used by the import pipeline:
each turns one upstream markdown/JSON artifact into the plain dict shape the
shared import contract expects.
"""

from __future__ import annotations

import json
import re
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


# --------------------------------------------------------------------------- #
# Parsing helpers — upstream artifact -> import-contract dicts
# --------------------------------------------------------------------------- #

_MEMORY_DIR = ("docs", "pdlc", "memory")


def _memory_dir(root: Path) -> Path:
    """Return the upstream memory directory for ``root``."""
    return root.joinpath(*_MEMORY_DIR)


def _split_table_row(line: str) -> list[str]:
    """Split a markdown table row into trimmed cell values (no leading/trailing
    empties from the surrounding pipes)."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    """True for a markdown header separator row like ``|---|---|``."""
    return bool(cells) and all(set(c) <= {"-", ":"} and c for c in cells)


def parse_decisions(root: Path) -> list[dict]:
    """Parse ``DECISIONS.md`` ``## D-NNN — title`` blocks.

    Returns a list of ``{"id", "title", "date", "rationale"}`` in document
    order. Missing ``Date``/``Rationale`` fields become empty strings.
    """
    path = _memory_dir(root) / "DECISIONS.md"
    if not path.exists():
        return []

    text = path.read_text()
    out: list[dict] = []
    # Match "## D-001 — title" up to the next "## " (or end of file).
    pattern = re.compile(
        r"^##\s+(D-\d+)\s*[—-]\s*(.+?)\s*$(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        dec_id, title, body = m.group(1), m.group(2), m.group(3)
        date_m = re.search(r"\*\*Date:\*\*\s*(.+)", body)
        rat_m = re.search(r"\*\*Rationale:\*\*\s*(.+)", body)
        out.append(
            {
                "id": dec_id.strip(),
                "title": title.strip(),
                "date": date_m.group(1).strip() if date_m else "",
                "rationale": rat_m.group(1).strip() if rat_m else "",
            }
        )
    return out


def parse_tasks(root: Path) -> list[dict]:
    """Parse ``.beads/tasks.json`` into import-contract task dicts.

    Maps the upstream ``id`` field to ``external_id`` so the engine can
    preserve ``bd-NN`` identifiers across the import.
    """
    path = root / ".beads" / "tasks.json"
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    out: list[dict] = []
    for t in data.get("tasks", []):
        out.append(
            {
                "external_id": t.get("id", ""),
                "title": t.get("title", ""),
                "labels": list(t.get("labels", [])),
                "status": t.get("status", ""),
            }
        )
    return out


def parse_deployments(root: Path) -> list[dict]:
    """Parse ``DEPLOYMENTS.md`` environment blocks + history tables.

    Each deployment-history row becomes ``{"env", "tier", "version", "date"}``,
    with ``env``/``tier`` drawn from the enclosing ``### Environment:`` block.
    """
    path = _memory_dir(root) / "DEPLOYMENTS.md"
    if not path.exists():
        return []

    text = path.read_text()
    out: list[dict] = []
    # Split into per-environment blocks; the slice before the first heading is
    # discarded (it holds no environment context).
    blocks = re.split(r"^###\s+Environment:\s*", text, flags=re.MULTILINE)[1:]
    for block in blocks:
        lines = block.splitlines()
        env = lines[0].strip() if lines else ""
        tier = ""
        in_history = False
        for line in lines[1:]:
            stripped = line.strip()
            tier_m = re.match(r"\|\s*tier\s*\|\s*(.+?)\s*\|", stripped)
            if tier_m:
                tier = tier_m.group(1).strip()
            if stripped.lower().startswith("#### deployment history"):
                in_history = True
                continue
            if in_history and stripped.startswith("#"):
                in_history = False  # next sub-heading ends the table
            if not (in_history and stripped.startswith("|")):
                continue
            cells = _split_table_row(stripped)
            if _is_separator_row(cells):
                continue
            if cells and cells[0].lower() == "date":
                continue  # header row
            if len(cells) >= 2:
                out.append(
                    {
                        "env": env,
                        "tier": tier,
                        "version": cells[1],
                        "date": cells[0],
                    }
                )
    return out


def parse_phase_history(root: Path) -> list[dict]:
    """Parse the ``## Phase History`` table in ``STATE.md``.

    Returns ``{"ts", "event", "phase", "sub_phase", "feature"}`` rows in
    document order. The ``—`` placeholder and ``none`` are normalised to
    empty / ``None``-ish values left as-is for callers to interpret.
    """
    path = _memory_dir(root) / "STATE.md"
    if not path.exists():
        return []

    text = path.read_text()
    m = re.search(
        r"^##\s+Phase History\s*$(.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        return []

    out: list[dict] = []
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_table_row(stripped)
        if _is_separator_row(cells) or len(cells) < 5:
            continue
        if cells[0].lower() == "timestamp":
            continue  # header row
        out.append(
            {
                "ts": cells[0],
                "event": cells[1],
                "phase": cells[2],
                "sub_phase": cells[3],
                "feature": cells[4],
            }
        )
    return out


def parse_roadmap(root: Path) -> dict[str, str]:
    """Parse ``ROADMAP.md`` into a ``{feature_name: F-NNN}`` map."""
    path = _memory_dir(root) / "ROADMAP.md"
    if not path.exists():
        return {}

    text = path.read_text()
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_table_row(stripped)
        if _is_separator_row(cells) or len(cells) < 2:
            continue
        fid, feature = cells[0], cells[1]
        if re.fullmatch(r"F-\d+", fid):
            mapping[feature] = fid
    return mapping


def read_memory_files(root: Path) -> list[dict]:
    """Read every ``*.md`` memory file into ``{"kind", "path", "body"}``.

    ``kind`` is the filename stem upper-cased (e.g. ``CONSTITUTION``). Output
    is sorted by path for deterministic ordering.
    """
    mem_dir = _memory_dir(root)
    if not mem_dir.exists():
        return []

    out: list[dict] = []
    for p in sorted(mem_dir.glob("*.md")):
        out.append(
            {
                "kind": p.stem.upper(),
                "path": str(p),
                "body": p.read_text(),
            }
        )
    return out
