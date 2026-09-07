"""Bind TOKOIN reservations to their initiating Owner.

Revision ID: 0031_tokoin_control_plane_owner
Revises: 0030_tokoin_signed_transactions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_tokoin_control_plane_owner"
down_revision = "0030_tokoin_signed_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tokoin_reservations",
        sa.Column(
            "requested_by_owner_id",
            sa.String(30),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_tokoin_reservations_owner",
        "tokoin_reservations",
        ["requested_by_owner_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tokoin_reservations_owner", table_name="tokoin_reservations")
    op.drop_column("tokoin_reservations", "requested_by_owner_id")
