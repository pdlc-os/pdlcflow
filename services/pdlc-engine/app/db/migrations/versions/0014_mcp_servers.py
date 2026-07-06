"""mcp_servers + mcp_bindings — org-scoped MCP tool-server registry (PRD-09).

allowed_tools = '{}' means DENY ALL: admins consciously allow each tool (the
test probe's tool list makes that a checkbox exercise). Auth is a secretstore
ref, write-only, never serialized. Bindings attach a server to a persona and
optionally a phase; unbound servers are inert. RLS-FORCEd on both tables.
"""

from alembic import op

revision = "0014_mcp_servers"
down_revision = "0013_persona_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "create table if not exists mcp_servers ("
        "  id uuid primary key,"
        "  org_id uuid not null references organizations(id) on delete cascade,"
        "  name text not null,"
        "  transport text not null check (transport in ('http','stdio')),"
        "  url text,"
        "  command text,"
        "  args jsonb not null default '[]'::jsonb,"
        "  auth_secret_ref text,"
        "  allowed_tools jsonb not null default '[]'::jsonb,"
        "  enabled boolean not null default true,"
        "  created_at timestamptz not null default now(),"
        "  unique (org_id, name),"
        "  check ((transport = 'http' and url is not null) "
        "      or (transport = 'stdio' and command is not null))"
        ")"
    )
    op.execute(
        "create table if not exists mcp_bindings ("
        "  id uuid primary key,"
        "  org_id uuid not null references organizations(id) on delete cascade,"
        "  server_id uuid not null references mcp_servers(id) on delete cascade,"
        "  persona text not null check (persona in "
        "    ('atlas','bolt','echo','friday','jarvis','muse','neo','phantom','pulse','sentinel')),"
        "  phase text check (phase in "
        "    ('Initialization','Inception','Construction','Operation'))"
        ")"
    )
    op.execute(
        "create unique index if not exists mcp_bindings_unique on mcp_bindings "
        "(server_id, persona, coalesce(phase, ''))"
    )
    for t in ("mcp_servers", "mcp_bindings"):
        op.execute(f"alter table {t} enable row level security")
        op.execute(f"alter table {t} force row level security")
        op.execute(
            f"create policy {t}_org_isolation on {t} "
            f"using (org_id::text = current_setting('app.org_id', true)) "
            f"with check (org_id::text = current_setting('app.org_id', true))"
        )


def downgrade() -> None:
    op.execute("drop table if exists mcp_bindings")
    op.execute("drop table if exists mcp_servers")
