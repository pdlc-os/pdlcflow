"""extra_headers — org-level extra request headers for relay gateways
(PRD-08). Guardrailed at the API (max 8, name/value limits, Authorization and
friends rejected — headers are routing hints, never a second credential
channel). Nullable, additive, no backfill.
"""

from alembic import op

revision = "0012_extra_headers"
down_revision = "0011_pricing_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table org_llm_config add column if not exists extra_headers jsonb")


def downgrade() -> None:
    op.execute("alter table org_llm_config drop column if exists extra_headers")
