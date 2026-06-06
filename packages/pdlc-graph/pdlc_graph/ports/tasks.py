"""Task store port — the Beads replacement (plan §6.1 `tasks` table).

Default: in-memory, preserving the upstream `bd-NN` external-id convention so
migrated projects keep their muscle memory. Engine injects a Postgres-backed
store. Atomic branch-claim semantics live in the engine adapter; the in-memory
store is only rich enough for the Plan sub-phase + tests.
"""

from __future__ import annotations

from typing import Protocol


class TaskStore(Protocol):
    def create(
        self, org_id: str, project_id: str, title: str, body: str, labels: list[str],
        external_id: str | None = None,
    ) -> str: ...
    def add_dependency(
        self, org_id: str, project_id: str, blocker_external_id: str, blocked_external_id: str
    ) -> None: ...
    def list(self, org_id: str, project_id: str) -> list[dict]: ...
    def claim(
        self, org_id: str, project_id: str, external_id: str, branch: str, claimed_by: str
    ) -> bool: ...


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, dict] = {}
        self._counter = 0

    def create(
        self, org_id: str, project_id: str, title: str, body: str, labels: list[str],
        external_id: str | None = None,
    ) -> str:
        # Preserve a caller-supplied external_id (migration path); else mint bd-N.
        if external_id is None:
            self._counter += 1
            external_id = f"bd-{self._counter}"
        self._tasks[external_id] = {
            "external_id": external_id,
            "org_id": org_id,
            "project_id": project_id,
            "title": title,
            "body": body,
            "labels": list(labels),
            "status": "open",
            "depends_on": [],
            "branch": None,
            "claimed_by": None,
        }
        return external_id

    def add_dependency(
        self, org_id: str, project_id: str, blocker_external_id: str, blocked_external_id: str
    ) -> None:
        if blocker_external_id not in self._tasks or blocked_external_id not in self._tasks:
            raise KeyError("both tasks must exist before a dependency is declared")
        self._tasks[blocked_external_id]["depends_on"].append(blocker_external_id)

    def list(self, org_id: str, project_id: str) -> list[dict]:
        return [t for t in self._tasks.values() if t["project_id"] == project_id]

    def claim(
        self, org_id: str, project_id: str, external_id: str, branch: str, claimed_by: str
    ) -> bool:
        """Atomically claim a task onto a branch. Returns False if the branch is
        already taken in the project (mirrors the unique partial index) or the
        task is already claimed."""
        task = self._tasks.get(external_id)
        if task is None or task.get("branch"):
            return False
        taken = any(
            t["project_id"] == task["project_id"] and t.get("branch") == branch
            for t in self._tasks.values()
        )
        if taken:
            return False
        task["branch"] = branch
        task["claimed_by"] = claimed_by
        task["status"] = "claimed"
        return True


_store: TaskStore = InMemoryTaskStore()


def set_task_store(store: TaskStore) -> None:
    global _store
    _store = store


def reset_task_store() -> None:
    global _store
    _store = InMemoryTaskStore()


def get_task_store() -> TaskStore:
    return _store
