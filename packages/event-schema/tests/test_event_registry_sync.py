"""registry.md ⇔ EVENT_TYPES stay in sync (enforced in the blocking CI job).

This is the guard that was missing when 17 event types drifted undocumented
(stub-gaps T4-1). Import path: the check script lives in scripts/, added to
sys.path here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from check_event_registry import check  # noqa: E402


def test_registry_matches_event_types():
    problems = check()
    assert not problems, "event registry drift:\n" + "\n".join(problems)
