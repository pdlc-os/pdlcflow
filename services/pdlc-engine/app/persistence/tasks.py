"""Postgres task store — the durable Beads replacement (plan §6.1 `tasks`).

Implements the pdlc_graph TaskStore interface over the `tasks` table using a
sync SQLAlchemy engine (graph nodes call it synchronously). Preserves a
caller-supplied `external_id` (migration path), else mints `bd-N` per project.
`claim` is a single atomic UPDATE guarded by the unique partial index on
(project_id, branch) — the upstream "one branch per task" semantic.

Verified via docker-compose (no Postgres in CI).
"""

from __future__ import annotations

import logging

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from ..db.models import Task
from ..db.session import get_sync_engine

log = logging.getLogger("pdlc.persistence.tasks")


class PostgresTaskStore:
    def __init__(self, settings) -> None:
        self._engine = get_sync_engine(settings)

    def create(
        self, org_id: str, project_id: str, title: str, body: str, labels: list[str],
        external_id: str | None = None,
    ) -> str:
        with self._engine.begin() as conn:
            if external_id is None:
                n = conn.execute(
                    select(func.count()).select_from(Task).where(Task.project_id == project_id)
                ).scalar() or 0
                external_id = f"bd-{n + 1}"
            conn.execute(
                insert(Task).values(
                    org_id=org_id,
                    project_id=project_id,
                    external_id=external_id,
                    title=title,
                    body=body,
                    labels=list(labels),
                    status="open",
                    depends_on=[],
                )
            )
        return external_id

    def add_dependency(self, project_id: str, blocker_external_id: str, blocked_external_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                update(Task)
                .where(Task.project_id == project_id, Task.external_id == blocked_external_id)
                .values(depends_on=func.array_append(Task.depends_on, blocker_external_id))
            )

    def list(self, project_id: str) -> list[dict]:
        with self._engine.begin() as conn:
            rows = conn.execute(
                select(Task).where(Task.project_id == project_id).order_by(Task.external_id)
            ).mappings().all()
        return [dict(r) for r in rows]

    def claim(self, project_id: str, external_id: str, branch: str, claimed_by: str) -> bool:
        """Atomic claim. Returns False if the task is already claimed or the
        branch is taken in the project (rejected by the unique partial index)."""
        try:
            with self._engine.begin() as conn:
                res = conn.execute(
                    update(Task)
                    .where(
                        Task.project_id == project_id,
                        Task.external_id == external_id,
                        Task.branch.is_(None),
                    )
                    .values(branch=branch, claimed_by=claimed_by, status="claimed")
                )
                return res.rowcount == 1
        except IntegrityError:
            return False
