"""hierarchy redesign RLS — the new tables/columns themselves are created by
0001's `Base.metadata.create_all` (schema follows the models). This migration only
applies row-level security to the new tables:

- Org-scoped (repositories, squad_initiatives, initiative_repositories,
  program_initiatives): standard org policy (RLS FORCE).
- `programs` is the cross-org umbrella: its OWNER org has full access, and any org
  with a linked initiative may READ it — so initiatives stay org-isolated while the
  program is shared.

Pre-deployment (no data yet).
"""

from alembic import op

revision = "0006_hierarchy"
down_revision = "0005_thread_transcript"
branch_labels = None
depends_on = None

_ORG_SCOPED = ("repositories", "squad_initiatives", "initiative_repositories", "program_initiatives")


def upgrade() -> None:
    for t in _ORG_SCOPED:
        op.execute(f"alter table {t} enable row level security")
        op.execute(f"alter table {t} force row level security")
        op.execute(
            f"create policy {t}_org_isolation on {t} "
            "using (org_id::text = current_setting('app.org_id', true)) "
            "with check (org_id::text = current_setting('app.org_id', true))"
        )

    # programs (cross-org): owner does everything; linked orgs may read.
    op.execute("alter table programs enable row level security")
    op.execute("alter table programs force row level security")
    op.execute(
        "create policy programs_owner on programs "
        "using (owner_org_id::text = current_setting('app.org_id', true)) "
        "with check (owner_org_id::text = current_setting('app.org_id', true))"
    )
    op.execute(
        "create policy programs_linked_read on programs for select "
        "using (id in (select program_id from program_initiatives "
        "where org_id::text = current_setting('app.org_id', true)))"
    )


def downgrade() -> None:
    op.execute("drop policy if exists programs_linked_read on programs")
    op.execute("drop policy if exists programs_owner on programs")
    op.execute("alter table programs no force row level security")
    op.execute("alter table programs disable row level security")
    for t in _ORG_SCOPED:
        op.execute(f"drop policy if exists {t}_org_isolation on {t}")
        op.execute(f"alter table {t} no force row level security")
        op.execute(f"alter table {t} disable row level security")
