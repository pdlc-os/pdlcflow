"""pricing_override + org budgets (PRD-07).

`org_llm_config.pricing_override` is the column pricing.py's docstring promised
("Tenants can override via org_llm_config.pricing_override"). `org_budgets`
holds the org's monthly soft limit + alert thresholds; `org_budget_alerts` is
the dedupe ledger — its PK guarantees one alert per (org, month, threshold)
even with concurrent workers. Both RLS-FORCEd like their siblings.
"""

from alembic import op

revision = "0011_pricing_budgets"
down_revision = "0010_llm_config_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table org_llm_config add column if not exists pricing_override jsonb")
    op.execute(
        "create table if not exists org_budgets ("
        "  org_id uuid primary key references organizations(id) on delete cascade,"
        "  monthly_limit_usd numeric(12,2) not null,"
        "  alert_pcts jsonb not null default '[50, 80, 100]'::jsonb,"
        "  updated_at timestamptz not null default now()"
        ")"
    )
    op.execute(
        "create table if not exists org_budget_alerts ("
        "  org_id uuid not null references organizations(id) on delete cascade,"
        "  month date not null,"
        "  pct integer not null,"
        "  fired_at timestamptz not null default now(),"
        "  primary key (org_id, month, pct)"
        ")"
    )
    for t in ("org_budgets", "org_budget_alerts"):
        op.execute(f"alter table {t} enable row level security")
        op.execute(f"alter table {t} force row level security")
        op.execute(
            f"create policy {t}_org_isolation on {t} "
            f"using (org_id::text = current_setting('app.org_id', true)) "
            f"with check (org_id::text = current_setting('app.org_id', true))"
        )


def downgrade() -> None:
    op.execute("drop table if exists org_budget_alerts")
    op.execute("drop table if exists org_budgets")
    op.execute("alter table org_llm_config drop column if exists pricing_override")
