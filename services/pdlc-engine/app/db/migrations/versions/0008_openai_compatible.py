"""openai_compatible — widen the provider CHECK constraints so org/agent LLM
config can select the generic OpenAI-protocol provider (relay gateways +
self-hosted servers).

The original constraints were UNNAMED (Postgres auto-named them, and rewrites
`IN` to `= ANY(...)` in pg_get_constraintdef), so we discover them by
introspection and recreate them NAMED — future widenings become deterministic
one-liners.
"""

from alembic import op
from sqlalchemy import text

revision = "0008_openai_compatible"
down_revision = "0007_provider_health"
branch_labels = None
depends_on = None

_WIDE = ("'bedrock','anthropic','vertex','azure','openai','gemini',"
         "'ollama','openai_compatible'")
_NARROW = "'bedrock','anthropic','vertex','azure','openai','gemini','ollama'"

_TABLES = {
    "org_llm_config": "ck_org_llm_config_provider",
    "agent_llm_config": "ck_agent_llm_config_provider",
}


def _drop_provider_checks(table: str) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text(
            "select conname from pg_constraint "
            "where conrelid = cast(:t as regclass) and contype = 'c' "
            "and pg_get_constraintdef(oid) ilike '%provider%' "
            "and pg_get_constraintdef(oid) not ilike '%agent_persona%'"
        ),
        {"t": table},
    ).scalars().all()
    for name in rows:
        op.execute(f'alter table {table} drop constraint "{name}"')


def upgrade() -> None:
    for table, name in _TABLES.items():
        _drop_provider_checks(table)
        op.execute(
            f"alter table {table} add constraint {name} "
            f"check (provider in ({_WIDE}))"
        )


def downgrade() -> None:
    # Fails (by design) if any row already uses openai_compatible.
    for table, name in _TABLES.items():
        _drop_provider_checks(table)
        op.execute(
            f"alter table {table} add constraint {name} "
            f"check (provider in ({_NARROW}))"
        )
