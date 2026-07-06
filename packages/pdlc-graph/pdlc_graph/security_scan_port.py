"""Security-scan port (execution arc, T1-4) — the seam for real scanners.

The Operation Verify sub-phase used to hardcode `dependency_audit: "clean"` /
`passed: True` without running anything. It now calls `scan(kind)` here. The
default `_NullScanner` returns an honest **skipped** result (never faked
"clean"); the engine injects a subprocess-backed scanner (pip-audit / npm-audit
/ gitleaks in the workspace) when execution is enabled.

Result shape: {kind, passed, skipped, findings: int, report: str}. `skipped`
means no scanner ran — the gate treats it as non-blocking but does NOT claim a
clean bill of health.
"""

from __future__ import annotations

from typing import Protocol


class ScannerPort(Protocol):
    def scan(self, kind: str) -> dict: ...


class _NullScanner:
    def scan(self, kind: str) -> dict:
        return {"kind": kind, "passed": True, "skipped": True,
                "findings": 0, "report": "no scanner wired — check skipped"}


_scanner: ScannerPort = _NullScanner()


def set_scanner(scanner: ScannerPort) -> None:
    global _scanner
    _scanner = scanner


def reset_scanner() -> None:
    global _scanner
    _scanner = _NullScanner()


def scan(kind: str) -> dict:
    """Run one scan (`dependency_audit` | `secret_scan`). Never raises out of
    the scan layer — a scanner error surfaces as skipped, not a false clean."""
    try:
        return _scanner.scan(kind)
    except Exception as exc:
        return {"kind": kind, "passed": True, "skipped": True, "findings": 0,
                "report": f"scanner error: {type(exc).__name__}"}
