"""Sprint 01.1: outbox operational visibility — delivery attempt counter.

Revision ID: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "event_outbox",
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("event_outbox", "attempts")
