"""Enforce one TOKOIN wallet per Agent.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_tokoin_wallets_agent_id",
        "tokoin_wallets",
        ["agent_id"],
        unique=True,
        postgresql_where="agent_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_tokoin_wallets_agent_id", table_name="tokoin_wallets")
