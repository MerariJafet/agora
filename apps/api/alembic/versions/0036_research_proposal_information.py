"""Add auditable research proposal information revisions.

Revision ID: 0036_research_information
Revises: 0035_validator_reconcile
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036_research_information"
down_revision = "0035_validator_reconcile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_proposal_information_updates",
        sa.Column("information_id", sa.String(30), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "provided_by_agent_id",
            sa.String(30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("prior_revision", sa.Integer(), nullable=False),
        sa.Column("new_revision", sa.Integer(), nullable=False),
        sa.Column("prior_state", sa.String(32), nullable=False),
        sa.Column("resulting_state", sa.String(32), nullable=False),
        sa.Column("prior_content_hash", sa.String(64), nullable=False),
        sa.Column("new_content_hash", sa.String(64), nullable=False),
        sa.Column("information", postgresql.JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provided_by_agent_id",
            "idempotency_key",
            name="uq_research_information_actor_idem",
        ),
        sa.UniqueConstraint(
            "proposal_id", "new_revision", name="uq_research_information_revision"
        ),
        sa.CheckConstraint(
            "new_revision = prior_revision + 1",
            name="ck_research_information_revision_increment",
        ),
    )
    op.create_index(
        "ix_research_information_proposal",
        "research_proposal_information_updates",
        ["proposal_id", "new_revision"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_information_proposal",
        table_name="research_proposal_information_updates",
    )
    op.drop_table("research_proposal_information_updates")
