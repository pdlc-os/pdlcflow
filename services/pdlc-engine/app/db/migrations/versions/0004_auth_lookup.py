"""auth_lookup — SECURITY DEFINER login so org_members can be RLS-locked too

Closes the one gap from `0003`: `org_members` was left out of RLS because login
resolves a user's org *by email before any org context exists*. This migration
adds a narrow `SECURITY DEFINER` function that does only that lookup (running as
its superuser owner, so it bypasses RLS — even FORCE), then re-enables + FORCEs
RLS on `org_members`. The app role gets EXECUTE on the function and nothing else
on the table, so it can log a user in but cannot read another org's membership.

Verified against real Postgres (the integration job).
"""

from alembic import op

revision = "0004_auth_lookup"
down_revision = "0003_rls_force"
branch_labels = None
depends_on = None

_FN = """
create or replace function auth_lookup(p_email text)
returns table(user_id uuid, org_id uuid, role text, password_hash text)
language sql stable security definer set search_path = public as $fn$
    select u.id, m.org_id, m.role, u.password_hash
    from users u
    join org_members m on m.user_id = u.id
    where u.email = p_email::citext
    limit 1
$fn$;
"""


def upgrade() -> None:
    op.execute(_FN)
    # Lock the function down: only the app role may call it (not PUBLIC).
    op.execute("revoke all on function auth_lookup(text) from public")
    op.execute(
        "do $$ begin if exists (select from pg_roles where rolname='pdlc_app') "
        "then grant execute on function auth_lookup(text) to pdlc_app; end if; end $$;"
    )
    # Put org_members back under RLS + FORCE (0003 had disabled it).
    op.execute("alter table org_members enable row level security")
    op.execute("alter table org_members force row level security")
    op.execute(
        "create policy org_members_org_isolation on org_members "
        "using (org_id::text = current_setting('app.org_id', true))"
    )


def downgrade() -> None:
    op.execute("drop policy if exists org_members_org_isolation on org_members")
    op.execute("alter table org_members no force row level security")
    op.execute("alter table org_members disable row level security")
    op.execute("drop function if exists auth_lookup(text)")
