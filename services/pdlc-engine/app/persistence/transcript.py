"""Durable per-thread conversation transcript — verbatim user + agent turns, so
the Studio can list past threads and replay/continue them (like ChatGPT history).

In-memory default; a Postgres-backed store (RLS-FORCEd, org-scoped) for self-host
/ SaaS. The engine records entries at each turn boundary (command, question
round, gate resolution, result).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import text

from ..db.rls import set_org_context
from ..db.session import get_sync_engine


def _now() -> str:
    return datetime.now(UTC).isoformat()


def summarize_pending(pending) -> str:
    """One-line agent-side transcript text for a PendingInteraction (or completion)."""
    if pending is None:
        return "(completed)"
    payload = getattr(pending, "payload", {}) or {}
    if getattr(pending, "kind", None) == "approval":
        return f"[approval: {getattr(pending, 'gate_kind', None) or 'gate'}] {payload.get('summary', '')}".strip()
    qs = payload.get("questions") or []
    return "[question] " + (qs[0] if qs else "awaiting your input")


class TranscriptStore(Protocol):
    def append(self, *, org_id, thread_id, role, text, project_id=None) -> None: ...
    def list_thread(self, *, org_id, thread_id) -> list[dict]: ...
    def list_threads(self, *, org_id, project_id=None) -> list[dict]: ...


def _label(entries: list[dict]) -> str:
    for e in entries:
        if e["role"] == "user" and e["text"].strip():
            return e["text"].strip()[:80]
    return "(thread)"


class InMemoryTranscriptStore:
    def __init__(self) -> None:
        self._rows: list[dict] = []

    def append(self, *, org_id, thread_id, role, text, project_id=None) -> None:
        self._rows.append({
            "org_id": str(org_id), "thread_id": str(thread_id),
            "project_id": str(project_id) if project_id else None,
            "seq": len(self._rows), "role": role, "text": text, "ts": _now(),
        })

    def list_thread(self, *, org_id, thread_id) -> list[dict]:
        rows = [r for r in self._rows if r["org_id"] == str(org_id) and r["thread_id"] == str(thread_id)]
        return [{"seq": r["seq"], "role": r["role"], "text": r["text"], "ts": r["ts"]}
                for r in sorted(rows, key=lambda r: r["seq"])]

    def list_threads(self, *, org_id, project_id=None) -> list[dict]:
        scoped = [r for r in self._rows if r["org_id"] == str(org_id)
                  and (not project_id or r["project_id"] == str(project_id))]
        by_thread: dict[str, list[dict]] = {}
        for r in scoped:
            by_thread.setdefault(r["thread_id"], []).append(r)
        out = []
        for tid, entries in by_thread.items():
            entries.sort(key=lambda r: r["seq"])
            out.append({"thread_id": tid, "project_id": entries[0]["project_id"],
                        "label": _label(entries), "turns": len(entries),
                        "last_ts": entries[-1]["ts"]})
        return sorted(out, key=lambda t: t["last_ts"], reverse=True)


class PostgresTranscriptStore:
    def __init__(self, settings) -> None:
        self._engine = get_sync_engine(settings)

    def append(self, *, org_id, thread_id, role, text, project_id=None) -> None:
        with self._engine.begin() as conn:
            set_org_context(conn, org_id)
            conn.execute(
                _text(
                    "insert into thread_transcript (org_id, thread_id, project_id, seq, role, body, ts) "
                    "values (:o, :t, :p, "
                    "  coalesce((select max(seq)+1 from thread_transcript where thread_id=:t), 0), "
                    "  :r, :b, now())"
                ),
                {"o": str(org_id), "t": str(thread_id),
                 "p": str(project_id) if project_id else None, "r": role, "b": text},
            )

    def list_thread(self, *, org_id, thread_id) -> list[dict]:
        with self._engine.begin() as conn:
            set_org_context(conn, org_id)
            rows = conn.execute(
                _text("select seq, role, body, ts from thread_transcript "
                      "where thread_id = :t order by seq asc"),
                {"t": str(thread_id)},
            ).mappings().all()
        return [{"seq": r["seq"], "role": r["role"], "text": r["body"],
                 "ts": r["ts"].isoformat() if hasattr(r["ts"], "isoformat") else str(r["ts"])}
                for r in rows]

    def list_threads(self, *, org_id, project_id=None) -> list[dict]:
        clauses = ["org_id = :o"]
        params: dict = {"o": str(org_id)}
        if project_id:
            clauses.append("project_id = :p")
            params["p"] = str(project_id)
        sql = _text(
            "select thread_id, max(project_id::text) as project_id, count(*) as turns, "
            "max(ts) as last_ts, "
            "(array_agg(body order by seq) filter (where role='user'))[1] as label "
            f"from thread_transcript where {' and '.join(clauses)} "
            "group by thread_id order by last_ts desc"
        )
        with self._engine.begin() as conn:
            set_org_context(conn, org_id)
            rows = conn.execute(sql, params).mappings().all()
        return [{"thread_id": r["thread_id"], "project_id": r["project_id"],
                 "label": (r["label"] or "(thread)")[:80], "turns": int(r["turns"]),
                 "last_ts": r["last_ts"].isoformat() if hasattr(r["last_ts"], "isoformat") else str(r["last_ts"])}
                for r in rows]


def _text(sql: str):
    return text(sql)


_store: TranscriptStore = InMemoryTranscriptStore()


def set_transcript_store(store: TranscriptStore) -> None:
    global _store
    _store = store


def reset_transcript_store() -> None:
    global _store
    _store = InMemoryTranscriptStore()


def get_transcript_store() -> TranscriptStore:
    return _store
