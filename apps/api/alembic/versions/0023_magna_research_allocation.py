"""MAGNA Sprint 02 research allocation market.

Revision ID: 0023_magna_research_allocation
Revises: 0022
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_magna_research_allocation"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_proposals",
        sa.Column("proposal_id", sa.String(length=30), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="PROPOSED"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("proposal_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("beneficial_controller_id", sa.String(length=120), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("constitution_hash", sa.String(length=64), nullable=False),
        sa.Column("charter_hash", sa.String(length=64), nullable=False),
        sa.Column("rule_evaluation_receipt_id", sa.String(length=30), nullable=True),
        sa.Column(
            "created_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("created_by_agent_version_id", sa.String(length=30), nullable=True),
        sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('PROPOSED','ELIGIBILITY_REVIEW','NEEDS_INFORMATION',"
            "'NEEDS_HUMAN_AUTHORITY','ELIGIBLE','RELEASED_ACTIVE','UNDER_REVIEW',"
            "'RESOLVED_VERIFIED','PAID','REJECTED','WITHDRAWN','DORMANT',"
            "'CLOSED_NONVIABLE','CLOSED_SAFETY')",
            name="ck_research_proposals_state",
        ),
        sa.CheckConstraint(
            "risk_level IN ('D0','D1','D2','D3','UNCLASSIFIED')",
            name="ck_research_proposals_risk",
        ),
        sa.UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_research_proposal_idem"
        ),
    )
    op.create_index(
        "ix_research_proposals_world_state", "research_proposals", ["world_id", "state"]
    )
    op.create_index(
        "ix_research_proposals_controller",
        "research_proposals",
        ["beneficial_controller_id"],
    )
    op.create_index("ix_research_proposals_hash", "research_proposals", ["content_hash"])

    op.create_table(
        "research_eligibility_reviews",
        sa.Column("review_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(length=30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "reviewer_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gate_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('PASS','NEEDS_INFORMATION','NEEDS_HUMAN_AUTHORITY','BLOCKED')",
            name="ck_research_eligibility_decision",
        ),
        sa.UniqueConstraint(
            "reviewer_agent_id", "idempotency_key", name="uq_eligibility_review_idem"
        ),
    )
    op.create_index(
        "ix_eligibility_reviews_proposal", "research_eligibility_reviews", ["proposal_id"]
    )

    op.create_table(
        "research_priority_assessments",
        sa.Column("assessment_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(length=30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "assessor_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("vector", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("uncertainty", sa.Integer(), nullable=False),
        sa.Column("pareto_layer", sa.Integer(), nullable=False),
        sa.Column("portfolio_score", sa.Integer(), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "assessor_agent_id", "idempotency_key", name="uq_priority_assessment_idem"
        ),
    )
    op.create_index(
        "ix_priority_assessments_proposal",
        "research_priority_assessments",
        ["proposal_id"],
    )
    op.create_index(
        "ix_priority_assessments_score",
        "research_priority_assessments",
        ["portfolio_score"],
    )

    op.create_table(
        "research_duplicate_links",
        sa.Column("duplicate_link_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "source_proposal_id",
            sa.String(length=30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column(
            "target_proposal_id",
            sa.String(length=30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column("link_type", sa.String(length=24), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_proposal_id <> target_proposal_id", name="ck_no_self_duplicate"),
        sa.UniqueConstraint(
            "source_proposal_id",
            "target_proposal_id",
            "created_by_agent_id",
            name="uq_duplicate_link_assertion",
        ),
    )
    op.create_index("ix_duplicate_links_source", "research_duplicate_links", ["source_proposal_id"])
    op.create_index("ix_duplicate_links_target", "research_duplicate_links", ["target_proposal_id"])

    op.create_table(
        "research_commitments",
        sa.Column("commitment_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(length=30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "agent_id", sa.String(length=30), sa.ForeignKey("agents.agent_id"), nullable=False
        ),
        sa.Column("beneficial_controller_id", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("resource_limits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "idempotency_key", name="uq_research_commitment_idem"),
        sa.UniqueConstraint("proposal_id", "agent_id", "role", name="uq_research_commitment_role"),
    )
    op.create_index("ix_research_commitments_proposal", "research_commitments", ["proposal_id"])

    op.create_table(
        "research_contribution_pools",
        sa.Column("pool_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(length=30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("terms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("created_by_agent_id", "idempotency_key", name="uq_research_pool_idem"),
    )
    op.create_index("ix_research_pools_proposal", "research_contribution_pools", ["proposal_id"])

    op.create_table(
        "research_release_epochs",
        sa.Column("epoch_id", sa.String(length=30), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("epoch_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("epoch_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("constitution_hash", sa.String(length=64), nullable=False),
        sa.Column("charter_hash", sa.String(length=64), nullable=False),
        sa.Column("candidate_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("selected_proposal_id", sa.String(length=30), nullable=True),
        sa.Column("reservation_id", sa.String(length=30), nullable=True),
        sa.Column("selection_receipt", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('RELEASED','NO_ELIGIBLE_CANDIDATE','FAILED_ESCROW',"
            "'SKIPPED_DOWNTIME','PAUSED_SAFETY','DISABLED')",
            name="ck_research_epoch_outcome",
        ),
        sa.UniqueConstraint("world_instance_id", "epoch_start", name="uq_research_epoch_slot"),
    )
    op.create_index("ix_research_epochs_outcome", "research_release_epochs", ["outcome"])

    op.create_table(
        "research_credit_reservations",
        sa.Column("reservation_id", sa.String(length=30), primary_key=True),
        sa.Column("asset", sa.String(length=32), nullable=False),
        sa.Column("amount_atomic", sa.BigInteger(), nullable=False),
        sa.Column(
            "proposal_id",
            sa.String(length=30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column("epoch_id", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="reserved"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("asset = 'RESEARCH_CREDITS_TEST'", name="ck_research_reservation_asset"),
        sa.CheckConstraint("amount_atomic = 100000000", name="ck_research_reservation_amount"),
        sa.UniqueConstraint(
            "proposal_id", "epoch_id", name="uq_research_reservation_proposal_epoch"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_research_reservation_idem"),
    )

    op.create_table(
        "research_appeals",
        sa.Column("appeal_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(length=30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("target", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_research_appeal_idem"
        ),
    )
    op.create_index("ix_research_appeals_proposal", "research_appeals", ["proposal_id"])


def downgrade() -> None:
    op.drop_index("ix_research_appeals_proposal", table_name="research_appeals")
    op.drop_table("research_appeals")
    op.drop_table("research_credit_reservations")
    op.drop_index("ix_research_epochs_outcome", table_name="research_release_epochs")
    op.drop_table("research_release_epochs")
    op.drop_index("ix_research_pools_proposal", table_name="research_contribution_pools")
    op.drop_table("research_contribution_pools")
    op.drop_index("ix_research_commitments_proposal", table_name="research_commitments")
    op.drop_table("research_commitments")
    op.drop_index("ix_duplicate_links_target", table_name="research_duplicate_links")
    op.drop_index("ix_duplicate_links_source", table_name="research_duplicate_links")
    op.drop_table("research_duplicate_links")
    op.drop_index("ix_priority_assessments_score", table_name="research_priority_assessments")
    op.drop_index("ix_priority_assessments_proposal", table_name="research_priority_assessments")
    op.drop_table("research_priority_assessments")
    op.drop_index("ix_eligibility_reviews_proposal", table_name="research_eligibility_reviews")
    op.drop_table("research_eligibility_reviews")
    op.drop_index("ix_research_proposals_hash", table_name="research_proposals")
    op.drop_index("ix_research_proposals_controller", table_name="research_proposals")
    op.drop_index("ix_research_proposals_world_state", table_name="research_proposals")
    op.drop_table("research_proposals")
