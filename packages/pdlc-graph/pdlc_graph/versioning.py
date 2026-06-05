"""Semantic-version bump from conventional commits (upstream 01-ship.md Step 6).

  BREAKING CHANGE / type! → major
  feat                    → minor
  fix/docs/chore/...      → patch
  ambiguous (feat + fix)  → minor (default)

Pure functions; no I/O.
"""

from __future__ import annotations

import re

_FEAT = re.compile(r"^feat(\(.+\))?:", re.IGNORECASE)
_BREAKING = re.compile(r"^[a-z]+(\(.+\))?!:|BREAKING CHANGE", re.IGNORECASE)


def bump_level(commits: list[str]) -> str:
    """Return 'major' | 'minor' | 'patch' for a list of commit subjects."""
    if not commits:
        return "patch"
    if any(_BREAKING.search(c) for c in commits):
        return "major"
    if any(_FEAT.search(c) for c in commits):
        return "minor"
    return "patch"


def _parse(version: str) -> tuple[int, int, int]:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version or "")
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def next_version(current: str | None, commits: list[str]) -> str:
    """Compute the next version tag (e.g. 'v1.3.0') from the current tag + commits."""
    major, minor, patch = _parse(current or "v0.0.0")
    level = bump_level(commits)
    if level == "major":
        major, minor, patch = major + 1, 0, 0
    elif level == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"v{major}.{minor}.{patch}"
