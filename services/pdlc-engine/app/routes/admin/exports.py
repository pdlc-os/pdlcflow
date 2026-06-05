"""CSV / ClickHouse query / DDL export for BI integration."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import Response

from ...analytics import get_analytics_store

router = APIRouter(prefix="/exports", tags=["admin", "exports"])


@router.get("/rollup.csv")
def export_rollup_csv(
    org_id: str = Query(...),
    dimension: str = Query(...),
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
) -> Response:
    rows = get_analytics_store().rollup(
        org_id=org_id, dimension=dimension, frm=frm, to=to
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["key", "events", "tokens", "usd"])
    for r in rows:
        writer.writerow([r["key"], r["events"], r["tokens"], r["usd"]])
    return Response(content=buf.getvalue(), media_type="text/csv")
