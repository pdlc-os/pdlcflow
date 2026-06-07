"""thread_transcript — durable per-thread conversation log (verbatim user + agent
turns) so the Studio can list past threads and replay/continue them.

RLS-FORCEd + org-isolated (org_id = app.org_id), like the other tenant tables.
Owner-created, so the init script's ALTER DEFAULT PRIVILEGES grants pdlc_app DML.
"""

from alembic import op

revision = "0005_thread_transcript"
down_revision = "0004_auth_lookup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "create table thread_transcript ("
        "  id bigserial primary key,"
        "  org_id uuid not null,"
        "  thread_id text not null,"
        "  project_id uuid,"
        "  seq integer not null,"
        "  role text not null,"
        "  body text not null,"
        "  ts timestamptz not null default now()"
        ")"
    )
    op.execute("create index ix_thread_transcript_thread on thread_transcript (thread_id, seq)")
    op.execute("create index ix_thread_transcript_org on thread_transcript (org_id, project_id)")
    op.execute("alter table thread_transcript enable row level security")
    op.execute("alter table thread_transcript force row level security")
    op.execute(
        "create policy thread_transcript_org_isolation on thread_transcript "
        "using (org_id::text = current_setting('app.org_id', true)) "
        "with check (org_id::text = current_setting('app.org_id', true))"
    )


def downgrade() -> None:
    op.execute("drop table if exists thread_transcript")
