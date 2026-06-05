"""rls — row-level security policies for tenant isolation (plan §6.3)

Enables RLS + an org-isolation policy on every org-scoped table. The policy
keys on `current_setting('app.org_id')`, which the engine sets per transaction
via `app.db.rls.set_org_context` (the FastAPI middleware / adapters do this at
the request/turn boundary).

Enforcement note: the policies are created and RLS is ENABLED, but NOT FORCEd.
The app currently connects as the table owner, which bypasses non-forced RLS —
so the engine keeps working while the project-scoped read methods (list/claim)
don't yet carry an org context. Full enforcement is a scoped follow-on:
(1) connect the app as a dedicated non-owner role, (2) `alter table … force row
level security`, (3) thread org_id through the remaining read methods so every
query sets `app.org_id` first. `set_org_context` is already applied on the write
+ analytics paths. Verified via docker-compose (no Postgres in CI).
"""

from alembic import op

revision = "0002_rls"
down_revision = "0001_init"
branch_labels = None
depends_on = None

# Tables with an `org_id` column that must be tenant-isolated.
_ORG_TABLES = [
    "org_members",
    "squads",
    "initiatives",
    "applications",
    "domains",
    "projects",
    "tasks",
    "memory_files",
    "approval_gates",
    "org_llm_config",
    "agent_llm_config",
    "events",
]


def upgrade() -> None:
    for t in _ORG_TABLES:
        op.execute(f"alter table {t} enable row level security")
        op.execute(
            f"create policy {t}_org_isolation on {t} "
            f"using (org_id::text = current_setting('app.org_id', true))"
        )


def downgrade() -> None:
    for t in _ORG_TABLES:
        op.execute(f"drop policy if exists {t}_org_isolation on {t}")
        op.execute(f"alter table {t} disable row level security")
