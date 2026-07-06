"""DB-backed persona prompt resolver (PRD-10 M1).

Injected into pdlc_graph's prompt-resolution seam at boot: for each
complete() call, the active org override for (turn's org, persona) is looked
up — None (no row / no DB / non-UUID org) falls back to the packaged
soul-spec inside the graph package. Per-(org, persona) TTL cache (60 s) plus
eager same-process invalidation on activation; multi-process staleness is
bounded by the TTL, acceptable for prompt changes.
"""

from __future__ import annotations

import logging
import time
import uuid as _uuid

from sqlalchemy import text

log = logging.getLogger("pdlc.runtime.prompts")

_TTL_S = 60.0
_cache: dict[tuple[str, str], tuple[str | None, float]] = {}


def invalidate_prompt_cache(org_id: str | None = None) -> None:
    if org_id is None:
        _cache.clear()
    else:
        for key in [k for k in _cache if k[0] == org_id]:
            _cache.pop(key, None)


class DBPromptResolver:
    def __init__(self, db) -> None:
        self._db = db

    def __call__(self, persona: str) -> str | None:
        from pdlc_graph.ports import current_org

        org = current_org()
        try:
            _uuid.UUID(str(org))
        except (ValueError, TypeError):
            return None  # self-host / outside a turn → packaged default
        key = (str(org), persona)
        hit = _cache.get(key)
        if hit is not None and hit[1] > time.monotonic():
            return hit[0]
        try:
            from ..db.rls import set_org_context

            with self._db.begin() as conn:
                set_org_context(conn, str(org))
                body = conn.execute(
                    text("select body from persona_prompts "
                         "where org_id = :o and persona = :p and status = 'active'"),
                    {"o": str(org), "p": persona},
                ).scalar()
        except Exception:  # prompt resolution must never break a turn
            return None
        _cache[key] = (body, time.monotonic() + _TTL_S)
        return body


def wire_prompt_resolver(settings) -> bool:
    """Inject the DB resolver when Postgres is configured. No flag: with no DB
    or no active rows the resolver is a transparent no-op."""
    if getattr(settings, "task_store", "memory") != "postgres":
        return False
    try:
        from pdlc_graph.personas import set_prompt_resolver

        from ..db.session import get_sync_engine

        set_prompt_resolver(DBPromptResolver(get_sync_engine(settings)))
        log.info("persona prompt resolver wired (org overrides active)")
        return True
    except Exception as exc:  # never block boot
        log.warning("prompt resolver wiring failed (%s); packaged specs only", exc)
        return False
