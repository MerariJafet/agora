"""University-signed agent delegation and owner-gated review proposals.

Revision ID: 0047_institution_agent
Revises: 0046_validator_package
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0047_institution_agent"
down_revision = "0046_validator_package"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "institution_agent_mandates",
        sa.Column("mandate_id", sa.String(30), primary_key=True),
        sa.Column(
            "institution_id",
            sa.String(30),
            sa.ForeignKey("research_institutions.institution_id"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("mandate_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_institution_agent_open_institution",
        "institution_agent_mandates",
        ["institution_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('PENDING', 'ACTIVE')"),
    )
    op.create_index(
        "uq_institution_agent_active_agent",
        "institution_agent_mandates",
        ["agent_id"],
        unique=True,
        postgresql_where=sa.text("state = 'ACTIVE'"),
    )
    op.create_table(
        "institution_agent_proposals",
        sa.Column("proposal_id", sa.String(30), primary_key=True),
        sa.Column(
            "mandate_id",
            sa.String(30),
            sa.ForeignKey("institution_agent_mandates.mandate_id"),
            nullable=False,
        ),
        sa.Column(
            "institution_id",
            sa.String(30),
            sa.ForeignKey("research_institutions.institution_id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(30),
            sa.ForeignKey("research_candidate_snapshots.candidate_id"),
            nullable=False,
        ),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("proposal_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("package_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("review_payload", postgresql.JSONB(), nullable=False),
        sa.Column("recommendation", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("reproduction_receipt", postgresql.JSONB(), nullable=True),
        sa.Column("tokoin_recommendation", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column(
            "supersedes_proposal_id",
            sa.String(30),
            sa.ForeignKey("institution_agent_proposals.proposal_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "mandate_id",
            "candidate_id",
            "proposal_version",
            name="uq_institution_agent_proposal_version",
        ),
    )
    op.create_index(
        "ix_institution_agent_proposals_candidate",
        "institution_agent_proposals",
        ["candidate_id", "state"],
    )
    op.create_table(
        "institution_agent_decisions",
        sa.Column("decision_id", sa.String(30), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(30),
            sa.ForeignKey("institution_agent_proposals.proposal_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("owner_id", sa.String(30), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("proposal_hash", sa.String(64), nullable=False),
        sa.Column("owner_notes", sa.Text(), nullable=False),
        sa.Column("signed_payload_hash", sa.String(64), nullable=True),
        sa.Column("institution_signature", sa.Text(), nullable=True),
        sa.Column("decision_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "institutional_reviews",
        sa.Column("agent_proposal_id", sa.String(30), nullable=True),
    )
    op.add_column(
        "institutional_reviews",
        sa.Column("institutional_notes", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_institutional_reviews_agent_proposal",
        "institutional_reviews",
        "institution_agent_proposals",
        ["agent_proposal_id"],
        ["proposal_id"],
    )
    op.create_unique_constraint(
        "uq_institutional_reviews_agent_proposal",
        "institutional_reviews",
        ["agent_proposal_id"],
    )
    op.add_column(
        "institutional_reviews",
        sa.Column("submitted_by_agent_id", sa.String(30), nullable=True),
    )
    op.create_foreign_key(
        "fk_institutional_reviews_submitting_agent",
        "institutional_reviews",
        "agents",
        ["submitted_by_agent_id"],
        ["agent_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_institutional_reviews_submitting_agent", "institutional_reviews", type_="foreignkey"
    )
    op.drop_column("institutional_reviews", "submitted_by_agent_id")
    op.drop_constraint(
        "uq_institutional_reviews_agent_proposal", "institutional_reviews", type_="unique"
    )
    op.drop_constraint(
        "fk_institutional_reviews_agent_proposal", "institutional_reviews", type_="foreignkey"
    )
    op.drop_column("institutional_reviews", "agent_proposal_id")
    op.drop_column("institutional_reviews", "institutional_notes")
    op.drop_table("institution_agent_decisions")
    op.drop_index(
        "ix_institution_agent_proposals_candidate", table_name="institution_agent_proposals"
    )
    op.drop_table("institution_agent_proposals")
    op.drop_index("uq_institution_agent_active_agent", table_name="institution_agent_mandates")
    op.drop_index(
        "uq_institution_agent_open_institution", table_name="institution_agent_mandates"
    )
    op.drop_table("institution_agent_mandates")
