from pathlib import Path

from pdlc_migrate.scan import Manifest, scan_project


def test_scan_empty_dir_returns_empty_manifest(tmp_path: Path):
    m = scan_project(tmp_path)
    assert isinstance(m, Manifest)
    assert m.summary == {
        "memory_files": 0, "episodes": 0, "bd_tasks": 0,
        "deployments": 0, "night_shift_runs": 0,
    }


def test_scan_recognizes_memory_files(tmp_path: Path):
    mem = tmp_path / "docs" / "pdlc" / "memory"
    mem.mkdir(parents=True)
    (mem / "CONSTITUTION.md").write_text("# constitution")
    (mem / "STATE.md").write_text("# state")
    (mem / "DEPLOYMENTS.md").write_text("# deployments")
    (mem / "episodes").mkdir()
    (mem / "episodes" / "001_first_2026-01-01.md").write_text("# episode")

    m = scan_project(tmp_path)
    assert m.summary["memory_files"] == 3
    assert m.summary["episodes"] == 1
    assert m.summary["deployments"] == 1
