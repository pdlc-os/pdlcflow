"""Task store port — the Beads replacement (plan §6.1 `tasks` table).

Default: in-memory, preserving the upstream `bd-NN` external-id convention so
migrated projects keep their muscle memory. Engine injects a Postgres-backed
store. Atomic branch-claim semantics live in the engine adapter; the in-memory
store is only rich enough for the Plan sub-phase + tests.
"""

from __future__ import annotations

from typing import Protocol


class TaskStore(Protocol):
    def create(self, project_id: str, title: str, body: str, labels: list[str]) -> str: ...
    def add_dependency(self, blocker_external_id: str, blocked_external_id: str) -> None: ...
    def list(self, project_id: str) -> list[dict]: ...


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, dict] = {}
        self._counter = 0

    def create(self, project_id: str, title: str, body: str, labels: list[str]) -> str:
        self._counter += 1
        ext = f"bd-{self._counter}"
        self._tasks[ext] = {
            "external_id": ext,
            "project_id": project_id,
            "title": title,
            "body": body,
            "labels": list(labels),
            "status": "open",
            "depends_on": [],
        }
        return ext

    def add_dependency(self, blocker_external_id: str, blocked_external_id: str) -> None:
        if blocker_external_id not in self._tasks or blocked_external_id not in self._tasks:
            raise KeyError("both tasks must exist before a dependency is declared")
        self._tasks[blocked_external_id]["depends_on"].append(blocker_external_id)

    def list(self, project_id: str) -> list[dict]:
        return [t for t in self._tasks.values() if t["project_id"] == project_id]


_store: TaskStore = InMemoryTaskStore()


def set_task_store(store: TaskStore) -> None:
    global _store
    _store = store


def reset_task_store() -> None:
    global _store
    _store = InMemoryTaskStore()


def get_task_store() -> TaskStore:
    return _store
