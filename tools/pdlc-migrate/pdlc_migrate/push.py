"""Push an upstream pdlc project to a running pdlc-engine.

Two pieces:

* :func:`build_import_payload` — PURE. Assembles the shared "import payload"
  contract from a scanned :class:`~pdlc_migrate.scan.Manifest` (or project root)
  plus a caller-supplied taxonomy and synthetic event list. It reads memory
  file bodies directly off the manifest and delegates task / decision /
  deployment extraction to the ``scan.parse_*`` helpers when they are present.
* :func:`push_payload` — POSTs the payload to ``{engine_url}/v1/migrate/import``
  over httpx. A transport may be injected so tests can run against the engine
  ASGI app in-process (``httpx.ASGITransport(app=...)``) with no network.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from . import scan as _scan
from .scan import Manifest, scan_project


def _as_manifest(manifest_or_root: Manifest | Path | str) -> Manifest:
    if isinstance(manifest_or_root, Manifest):
        return manifest_or_root
    return scan_project(Path(manifest_or_root))


def _call_parser(name: str, root: Path) -> list[dict[str, Any]]:
    """Invoke a ``scan.parse_*`` helper if it exists, else return ``[]``.

    The scan parsing helpers are owned by the scan module and may land
    independently; resolving them lazily keeps this module importable (and the
    push path usable) regardless of which helpers are available yet.
    """

    fn = getattr(_scan, name, None)
    if fn is None:
        return []
    return list(fn(root))


def build_import_payload(
    manifest_or_root: Manifest | Path | str,
    *,
    org_id: str,
    project_id: str,
    taxonomy: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the shared import contract (pure — no I/O to the engine).

    ``manifest_or_root`` may be an already-scanned :class:`Manifest` or a path
    to the upstream project root (which is scanned here). ``taxonomy`` and
    ``events`` are passed through verbatim into the payload.
    """

    manifest = _as_manifest(manifest_or_root)
    root = manifest.project_root

    memory_files = [
        {"kind": path.stem, "path": str(path), "body": path.read_text()}
        for path in manifest.memory_files
    ]

    return {
        "org_id": str(org_id),
        "project_id": str(project_id),
        "taxonomy": {
            "initiative": taxonomy.get("initiative"),
            "application": taxonomy.get("application"),
            "domains": list(taxonomy.get("domains", [])),
        },
        "memory_files": memory_files,
        "tasks": _call_parser("parse_tasks", root),
        "decisions": _call_parser("parse_decisions", root),
        "deployments": _call_parser("parse_deployments", root),
        "events": list(events),
    }


def push_payload(
    payload: dict[str, Any],
    engine_url: str,
    *,
    transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """POST the import payload to the engine and return its response.

    The response carries per-kind PERSISTED counts (events/memory_files/
    tasks/decisions/deployments), a ``received`` block mirroring the input,
    and an ``entities`` block with the resolved initiative/application ids.

    Pass ``transport=httpx.ASGITransport(app=engine_app)`` to drive the engine
    in-process (hermetic tests); omit it for a real network client. An async
    transport (e.g. ASGITransport) is driven through an :class:`httpx.AsyncClient`
    on a private event loop so the public surface stays synchronous.
    """

    url = f"{engine_url.rstrip('/')}/v1/migrate/import"

    if isinstance(transport, httpx.AsyncBaseTransport):
        async def _post() -> dict[str, Any]:
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()

        return asyncio.run(_post())

    with httpx.Client(transport=transport) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


def push_manifest(manifest_or_root: Manifest | Path | str, engine_url: str) -> dict[str, int]:
    """Convenience: scan/assemble with no taxonomy or backfilled events, then
    push. Taxonomy assignment and event backfill are separate CLI steps; this
    just ships memory files and the parsed entity rows.
    """

    payload = build_import_payload(
        manifest_or_root,
        org_id="00000000-0000-0000-0000-000000000000",
        project_id="00000000-0000-0000-0000-000000000000",
        taxonomy={"initiative": None, "application": None, "domains": []},
        events=[],
    )
    return push_payload(payload, engine_url)
