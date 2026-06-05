"""Admin access guard — enforce the cross-org analytics ban with an audit event.

Data routes pass their `org_id` (optional query param) through `require_org`.
A missing/blank org_id emits an `admin.access.denied` audit event and raises
403 — cross-org analytics are banned by design (plan §5.3).
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException

log = logging.getLogger("pdlc.admin.guard")

_ZERO = UUID(int=0)


def _audit_denied(label: str) -> None:
    try:
        from event_schema import EventEnvelope

        from ...clickstream import get_emitter

        env = EventEnvelope(
            event_type="admin.access.denied",
            org_id=_ZERO,
            project_id=_ZERO,
            payload={"path": label, "reason": "missing org_id"},
        )
        get_emitter().emit_envelope(env)
    except Exception as exc:  # best-effort audit; never mask the 403
        log.warning("admin.access.denied audit emit failed: %s", exc)


def require_org(org_id: str | None, label: str) -> str:
    if not org_id:
        _audit_denied(label)
        raise HTTPException(
            status_code=403,
            detail="org_id required — cross-org analytics are not permitted",
        )
    return org_id
