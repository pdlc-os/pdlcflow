"""persona_prompts — org-level persona soul-spec overrides (PRD-10).

Versions are IMMUTABLE rows: draft → active → archived; "editing" creates
version N+1. A partial unique index guarantees ≤1 active per (org, persona).
Sentinel is excluded by CHECK — it is a deterministic Python evaluator, not an
LLM, so a prompt override would be a lie. RLS-FORCEd like its siblings.
"""

from alembic import op

revision = "0013_persona_prompts"
down_revision = "0012_extra_headers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "create table persona_prompts ("
        "  id uuid primary key,"
        "  org_id uuid not null references organizations(id) on delete cascade,"
        "  persona text not null check (persona in "
        "    ('atlas','bolt','echo','friday','jarvis','muse','neo','phantom','pulse')),"
        "  version integer not null,"
        "  body text not null,"
        "  status text not null default 'draft' "
        "    check (status in ('draft','active','archived')),"
        "  created_by uuid references users(id) on delete set null,"
        "  created_at timestamptz not null default now(),"
        "  activated_at timestamptz,"
        "  unique (org_id, persona, version)"
        ")"
    )
    op.execute(
        "create unique index persona_prompts_one_active "
        "on persona_prompts (org_id, persona) where status = 'active'"
    )
    op.execute("alter table persona_prompts enable row level security")
    op.execute("alter table persona_prompts force row level security")
    op.execute(
        "create policy persona_prompts_org_isolation on persona_prompts "
        "using (org_id::text = current_setting('app.org_id', true)) "
        "with check (org_id::text = current_setting('app.org_id', true))"
    )


def downgrade() -> None:
    op.execute("drop table if exists persona_prompts")
