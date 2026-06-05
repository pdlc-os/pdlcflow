"""Dev sink — append-only JSON-Lines at ~/.pdlcflow/events.jsonl."""

from __future__ import annotations

import os
from pathlib import Path

from event_schema import EventEnvelope


class JsonlFileSink:
    def __init__(self, path: str | None = None):
        default = Path.home() / ".pdlcflow" / "events.jsonl"
        self._path = Path(path or os.environ.get("PDLC_JSONL_PATH", str(default)))
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, batch: list[EventEnvelope]) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            for e in batch:
                fh.write(e.model_dump_json())
                fh.write("\n")
