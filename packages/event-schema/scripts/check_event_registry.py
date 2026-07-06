#!/usr/bin/env python3
"""Guard: registry.md documents exactly the event types in EVENT_TYPES.

Drift here went unnoticed for 17 event types because this script — referenced
by registry.md and the monitoring wiki — never existed (stub-gaps T4-1). It
now does, and a hermetic test (tests/test_event_registry_sync.py) runs it in
the blocking event-schema CI job.

Checks, exit 1 with a readable diff on any failure:
  1. Every EVENT_TYPES entry is documented as a table row in registry.md.
  2. Every event documented in registry.md exists in EVENT_TYPES.
  3. The actor-classification sets (_HUMAN_EVENTS / _SYSTEM_EVENTS) are subsets
     of EVENT_TYPES (catches typos that would silently misclassify events).

Run directly (`python scripts/check_event_registry.py`) or import `check()`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REGISTRY = Path(__file__).resolve().parent.parent / "event_schema" / "registry.md"

# First-column backtick token of a markdown table row: `| \`event.name\` | … |`.
# Matches dotted (llm.failover) and dotless (error) event names alike.
_ROW_EVENT = re.compile(r"^\|\s*`([a-z_][a-z_.]*)`\s*\|", re.MULTILINE)


def documented_events(registry_path: Path = _REGISTRY) -> set[str]:
    return set(_ROW_EVENT.findall(registry_path.read_text()))


def check(registry_path: Path = _REGISTRY) -> list[str]:
    """Return a list of human-readable problems ([] == in sync)."""
    from event_schema.envelope import (
        _HUMAN_EVENTS,
        _SYSTEM_EVENTS,
        EVENT_TYPES,
    )

    documented = documented_events(registry_path)
    problems: list[str] = []

    missing = EVENT_TYPES - documented
    if missing:
        problems.append(
            "In EVENT_TYPES but NOT documented in registry.md "
            f"({len(missing)}): {', '.join(sorted(missing))}")

    extra = documented - EVENT_TYPES
    if extra:
        problems.append(
            "Documented in registry.md but NOT in EVENT_TYPES "
            f"({len(extra)}): {', '.join(sorted(extra))}")

    for name, group in (("_HUMAN_EVENTS", _HUMAN_EVENTS),
                        ("_SYSTEM_EVENTS", _SYSTEM_EVENTS)):
        stray = group - EVENT_TYPES
        if stray:
            problems.append(
                f"{name} contains non-EVENT_TYPES entries: {', '.join(sorted(stray))}")

    return problems


def main() -> int:
    problems = check()
    if problems:
        print("event registry OUT OF SYNC:\n", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\nUpdate event_schema/registry.md (+ payloads.py) to match "
              "EVENT_TYPES in event_schema/envelope.py.", file=sys.stderr)
        return 1
    from event_schema.envelope import EVENT_TYPES

    print(f"event registry in sync: {len(EVENT_TYPES)} event types documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
