"""rls force — enforce tenant isolation at the database (plan §6.3)

Phase 3 of the auth/RLS arc. `0002` ENABLEd RLS + policies but the app connected
as the table owner, which bypasses non-forced RLS. This migration:

1. **FORCE**s row-level security on the tenant-CONTENT tables, so RLS applies
   even to the owner — combined with the app connecting as a **non-superuser**
   role (`pdlc_app`, created by the compose init script / test setup), every
   query must `SET app.org_id` (via `db.rls.set_org_context`) or see no rows.

2. Takes **org_members OUT of RLS**. Login resolves a user's org by email
   *before* any org context exists, so the membership lookup can't be org-scoped
   without a chicken-and-egg. Membership is scoped at the app layer instead; a
   `SECURITY DEFINER` auth-lookup function is the documented hardening to also
   lock this at the DB.

Verified against real Postgres (docker-compose + the integration job).
"""

from alembic import op

revision = "0003_rls_force"
down_revision = "0002_rls"
branch_labels = None
depends_on = None

# Tenant-content tables — always queried with an org context, so safe to FORCE.
_FORCED = [
    "squads", "initiatives", "applications", "domains", "projects",
    "tasks", "memory_files", "approval_gates", "org_llm_config",
    "agent_llm_config", "events",
]


def upgrade() -> None:
    # org_members: drop the policy + disable RLS so the pre-context login lookup works.
    op.execute("drop policy if exists org_members_org_isolation on org_members")
    op.execute("alter table org_members disable row level security")

    for t in _FORCED:
        op.execute(f"alter table {t} force row level security")


def downgrade() -> None:
    for t in _FORCED:
        op.execute(f"alter table {t} no force row level security")
    op.execute("alter table org_members enable row level security")
    op.execute(
        "create policy org_members_org_isolation on org_members "
        "using (org_id::text = current_setting('app.org_id', true))"
    )
