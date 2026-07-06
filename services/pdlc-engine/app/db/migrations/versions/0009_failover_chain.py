"""failover_chain — ordered fallback provider configs on org_llm_config
(PRD-05 resilient routing). JSONB (vs child table): the chain is small (≤3),
ordered, always read whole with the parent row, and inherits the table's RLS
for free. Additive with default '[]' — zero behavior change until an org
configures a chain.
"""

from alembic import op

revision = "0009_failover_chain"
down_revision = "0008_openai_compatible"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "alter table org_llm_config "
        "add column failover_chain jsonb not null default '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("alter table org_llm_config drop column if exists failover_chain")
