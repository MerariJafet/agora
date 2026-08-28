"""World opportunity market V2.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "world_market_opportunities",
        sa.Column("opportunity_id", sa.String(length=30), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("market_class", sa.String(length=8), nullable=False, server_default="test"),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("district_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column(
            "created_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("created_by_agent_version_id", sa.String(length=30), nullable=True),
        sa.Column("related_mission_id", sa.String(length=30), nullable=True),
        sa.Column("related_challenge_mission_id", sa.String(length=30), nullable=True),
        sa.Column("related_artifact_version_id", sa.String(length=30), nullable=True),
        sa.Column("reward_aceros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("escrow_aceros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "market_class IN ('test','real','legacy')", name="ck_world_opportunities_market_class"
        ),
        sa.CheckConstraint(
            "state IN ('open','committed','withdrawn','expired','closed')",
            name="ck_world_opportunities_state",
        ),
        sa.CheckConstraint(
            "reward_aceros >= 0 AND escrow_aceros >= 0",
            name="ck_world_opportunities_nonnegative_aceros",
        ),
        sa.CheckConstraint(
            "reward_aceros = 0 OR escrow_aceros >= reward_aceros",
            name="ck_world_opportunities_escrow_covers_reward",
        ),
        sa.UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_world_opportunity_idempotency"
        ),
    )
    op.create_index(
        "ix_world_opportunities_district_state",
        "world_market_opportunities",
        ["district_id", "state"],
    )
    op.create_index(
        "ix_world_opportunities_market_class", "world_market_opportunities", ["market_class"]
    )

    op.create_table(
        "world_market_needs",
        sa.Column("need_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(length=30),
            sa.ForeignKey("world_market_opportunities.opportunity_id"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("market_class", sa.String(length=8), nullable=False, server_default="test"),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("district_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "requested_resources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column(
            "created_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("created_by_agent_version_id", sa.String(length=30), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "market_class IN ('test','real','legacy')", name="ck_world_needs_market_class"
        ),
        sa.CheckConstraint(
            "state IN ('open','committed','withdrawn','expired','closed')",
            name="ck_world_needs_state",
        ),
        sa.UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_world_need_idempotency"
        ),
    )
    op.create_index("ix_world_needs_district_state", "world_market_needs", ["district_id", "state"])

    op.create_table(
        "world_market_offers",
        sa.Column("offer_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "need_id",
            sa.String(length=30),
            sa.ForeignKey("world_market_needs.need_id"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("market_class", sa.String(length=8), nullable=False, server_default="test"),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("district_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "offered_resources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column(
            "created_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("created_by_agent_version_id", sa.String(length=30), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "market_class IN ('test','real','legacy')", name="ck_world_offers_market_class"
        ),
        sa.CheckConstraint(
            "state IN ('open','committed','withdrawn','expired','closed')",
            name="ck_world_offers_state",
        ),
        sa.UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_world_offer_idempotency"
        ),
    )
    op.create_index(
        "ix_world_offers_district_state", "world_market_offers", ["district_id", "state"]
    )

    op.create_table(
        "world_market_commitments",
        sa.Column("commitment_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "need_id",
            sa.String(length=30),
            sa.ForeignKey("world_market_needs.need_id"),
            nullable=False,
        ),
        sa.Column(
            "offer_id",
            sa.String(length=30),
            sa.ForeignKey("world_market_offers.offer_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("market_class", sa.String(length=8), nullable=False, server_default="test"),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="proposed"),
        sa.Column(
            "proposed_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column(
            "accepted_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=True,
        ),
        sa.Column(
            "terms", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "market_class IN ('test','real','legacy')", name="ck_world_commitments_market_class"
        ),
        sa.CheckConstraint(
            "state IN ('proposed','accepted','rejected','withdrawn','expired')",
            name="ck_world_commitments_state",
        ),
        sa.UniqueConstraint(
            "proposed_by_agent_id", "idempotency_key", name="uq_world_commitment_idempotency"
        ),
        sa.UniqueConstraint("need_id", "offer_id", name="uq_world_commitment_need_offer"),
    )
    op.create_index("ix_world_commitments_state", "world_market_commitments", ["state"])

    op.create_table(
        "world_market_contributions",
        sa.Column("contribution_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "commitment_id",
            sa.String(length=30),
            sa.ForeignKey("world_market_commitments.commitment_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("market_class", sa.String(length=8), nullable=False, server_default="test"),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_version_id", sa.String(length=30), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="delivered"),
        sa.Column(
            "created_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("created_by_agent_version_id", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "market_class IN ('test','real','legacy')", name="ck_world_contributions_market_class"
        ),
        sa.CheckConstraint(
            "state IN ('delivered','reviewed','withdrawn')", name="ck_world_contributions_state"
        ),
        sa.UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_world_contribution_idempotency"
        ),
    )
    op.create_index(
        "ix_world_contributions_commitment", "world_market_contributions", ["commitment_id"]
    )

    op.create_table(
        "world_market_outcomes",
        sa.Column("outcome_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "contribution_id",
            sa.String(length=30),
            sa.ForeignKey("world_market_contributions.contribution_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("market_class", sa.String(length=8), nullable=False, server_default="test"),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "reviewer_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("reviewer_agent_version_id", sa.String(length=30), nullable=True),
        sa.Column("settled_aceros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "market_class IN ('test','real','legacy')", name="ck_world_outcomes_market_class"
        ),
        sa.CheckConstraint(
            "verdict IN ('accepted','needs_revision','rejected')", name="ck_world_outcomes_verdict"
        ),
        sa.CheckConstraint("settled_aceros = 0", name="ck_world_outcomes_test_no_real_settlement"),
        sa.UniqueConstraint(
            "reviewer_agent_id", "idempotency_key", name="uq_world_outcome_idempotency"
        ),
    )
    op.create_index("ix_world_outcomes_contribution", "world_market_outcomes", ["contribution_id"])


def downgrade() -> None:
    op.drop_index("ix_world_outcomes_contribution", table_name="world_market_outcomes")
    op.drop_table("world_market_outcomes")
    op.drop_index("ix_world_contributions_commitment", table_name="world_market_contributions")
    op.drop_table("world_market_contributions")
    op.drop_index("ix_world_commitments_state", table_name="world_market_commitments")
    op.drop_table("world_market_commitments")
    op.drop_index("ix_world_offers_district_state", table_name="world_market_offers")
    op.drop_table("world_market_offers")
    op.drop_index("ix_world_needs_district_state", table_name="world_market_needs")
    op.drop_table("world_market_needs")
    op.drop_index("ix_world_opportunities_market_class", table_name="world_market_opportunities")
    op.drop_index("ix_world_opportunities_district_state", table_name="world_market_opportunities")
    op.drop_table("world_market_opportunities")
