"""llm_config_versions — immutable, append-only history of every org/agent LLM
config mutation (PRD-06). Each row stores the FULL PRIOR state as JSONB
(null = the row didn't exist), so rollback is "write the snapshot back" and
diffs are computed at read time — no dual bookkeeping. RLS-FORCEd + org-scoped
like the config tables it shadows.
"""

from alembic import op

revision = "0010_llm_config_versions"
down_revision = "0009_failover_chain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "create table llm_config_versions ("
        "  id uuid primary key,"
        "  org_id uuid not null references organizations(id) on delete cascade,"
        "  scope text not null,"                      # 'org' | '<persona>'
        "  change_kind text not null check (change_kind in "
        "    ('update','delete','rollback','import','preset_apply')),"
        "  snapshot jsonb,"                           # prior row state; null = didn't exist
        "  actor_user_id uuid references users(id) on delete set null,"
        "  actor_label text,"
        "  created_at timestamptz not null default now()"
        ")"
    )
    op.execute(
        "create index ix_llmcv_org_scope_created on llm_config_versions "
        "(org_id, scope, created_at desc)"
    )
    op.execute("alter table llm_config_versions enable row level security")
    op.execute("alter table llm_config_versions force row level security")
    op.execute(
        "create policy llm_config_versions_org_isolation on llm_config_versions "
        "using (org_id::text = current_setting('app.org_id', true)) "
        "with check (org_id::text = current_setting('app.org_id', true))"
    )


def downgrade() -> None:
    op.execute("drop table if exists llm_config_versions")
