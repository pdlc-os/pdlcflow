"""llm_provider_health — last probe result per (org, scope) so the console can
show provider status chips without re-probing on every page load. Written by
on-demand admin probes now; PRD-05's circuit-breaker transitions will write the
same table later.

Scopes are 'org-default' or 'agent:<persona>' (tenant state only — the
instance-default status lives in-process, see app/llm/probe.py).
RLS-FORCEd + org-isolated like the other tenant tables.
"""

from alembic import op

revision = "0007_provider_health"
down_revision = "0006_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "create table if not exists llm_provider_health ("
        "  org_id uuid not null references organizations(id) on delete cascade,"
        "  scope text not null,"
        "  provider text not null,"
        "  ok boolean not null,"
        "  latency_ms integer,"
        "  error_class text,"
        "  checked_at timestamptz not null default now(),"
        "  primary key (org_id, scope)"
        ")"
    )
    op.execute("alter table llm_provider_health enable row level security")
    op.execute("alter table llm_provider_health force row level security")
    op.execute(
        "create policy llm_provider_health_org_isolation on llm_provider_health "
        "using (org_id::text = current_setting('app.org_id', true)) "
        "with check (org_id::text = current_setting('app.org_id', true))"
    )


def downgrade() -> None:
    op.execute("drop table if exists llm_provider_health")
