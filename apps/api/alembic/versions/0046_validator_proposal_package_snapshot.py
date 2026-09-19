"""Preserve the exact blind evidence package submitted with each owner-gated proposal.

Revision ID: 0046_validator_package
Revises: 0045_merge_validator_owner_gate
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0046_validator_package"
down_revision = "0045_merge_validator_owner_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "validator_review_proposals",
        sa.Column("package_snapshot", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("validator_review_proposals", "package_snapshot")
