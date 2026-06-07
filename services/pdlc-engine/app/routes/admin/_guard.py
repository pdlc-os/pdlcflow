"""Admin access guard — tenant + role enforcement for the Nexus Console routes.

`admin_org(label)` returns a FastAPI dependency that resolves the effective org
for an admin data route:

- **auth off** → behaves like the original cross-org ban: an `org_id` query param
  is required (missing → 403 + `admin.access.denied`).
- **auth on**  → the org comes from the JWT (a mismatched `org_id` query is
  rejected), and the caller must hold the `admin`/`owner` role.

Routes use it as `org_id: str = Depends(admin_org("/admin/<route>"))`, replacing
both the raw query param and the old `require_org(...)` call.
"""

from __future__ import annotations

from fastapi import Depends, Query

from ...auth.local import Identity, get_principal, resolve_org


def admin_org(label: str):
    def _dep(
        org_id: str | None = Query(None),
        principal: Identity | None = Depends(get_principal),
    ) -> str:
        return resolve_org(principal, org_id, label, admin=True)

    return _dep
