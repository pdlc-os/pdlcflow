"""init — full PDLC schema

Creates the full multi-tenant schema (docs/.research §6 + §7 + the self-host
`events` table from §8) from the SQLAlchemy models. We build via
`Base.metadata.create_all` on the migration connection rather than hand-written
op.create_table — it yields the exact schema the models declare and stays in
sync with them. (Run `alembic revision --autogenerate` against a live DB later
to capture any index refinements.)
"""

from alembic import op
from app.db.models import Base

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("create extension if not exists pgcrypto")
    op.execute("create extension if not exists citext")
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
