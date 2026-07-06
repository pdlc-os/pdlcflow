"""org_quotas — per-org RPM override for the LLM rate limiter (T3-5).

The limiter shipped with only a global PDLC_LLM_RPM_DEFAULT; the docstring
promised per-org quotas via a "Quotas page". This is that row: a nullable
rpm_limit per org (null / no row ⇒ the global default applies). Kept separate
from org_budgets so an RPM cap doesn't require configuring a dollar budget.
RLS-FORCEd like its siblings.
"""

from alembic import op

revision = "0015_org_quotas"
down_revision = "0014_mcp_servers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "create table if not exists org_quotas ("
        "  org_id uuid primary key references organizations(id) on delete cascade,"
        "  rpm_limit integer,"
        "  updated_at timestamptz not null default now()"
        ")"
    )
    op.execute("alter table org_quotas enable row level security")
    op.execute("alter table org_quotas force row level security")
    op.execute(
        "create policy org_quotas_org_isolation on org_quotas "
        "using (org_id::text = current_setting('app.org_id', true)) "
        "with check (org_id::text = current_setting('app.org_id', true))"
    )


def downgrade() -> None:
    op.execute("drop table if exists org_quotas")
