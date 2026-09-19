"""Owner-gated synthetic institutional validator recommendations.

Revision ID: 0042_validator_owner_gate
Revises: 0041_mentions_network
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042_validator_owner_gate"
down_revision = "0041_mentions_network"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "validator_assignments",
        sa.Column("decision_owner_id", sa.String(30), nullable=True),
    )
    op.create_foreign_key(
        "fk_validator_assignments_decision_owner",
        "validator_assignments",
        "users",
        ["decision_owner_id"],
        ["user_id"],
    )
    op.execute(
        """
        UPDATE validator_assignments AS assignment
        SET decision_owner_id = COALESCE(
            validator.verified_by_owner_id,
            validator.representative_owner_id
        )
        FROM institutional_validators AS validator
        WHERE validator.validator_id = assignment.validator_id
          AND assignment.decision_owner_id IS NULL
        """
    )
    op.alter_column("validator_assignments", "decision_owner_id", nullable=False)
    op.create_index(
        "ix_validator_assignments_decision_owner",
        "validator_assignments",
        ["decision_owner_id", "state"],
    )

    op.create_table(
        "validator_review_proposals",
        sa.Column("proposal_id", sa.String(30), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.String(30),
            sa.ForeignKey("validator_assignments.assignment_id"),
            nullable=False,
        ),
        sa.Column(
            "validator_id",
            sa.String(30),
            sa.ForeignKey("institutional_validators.validator_id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(30),
            sa.ForeignKey("research_candidate_snapshots.candidate_id"),
            nullable=False,
        ),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("review_payload", postgresql.JSONB(), nullable=False),
        sa.Column("recommendation", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("tokoin_recommendation", postgresql.JSONB(), nullable=False),
        sa.Column("proposal_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column(
            "supersedes_proposal_id",
            sa.String(30),
            sa.ForeignKey("validator_review_proposals.proposal_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "assignment_id",
            "proposal_version",
            name="uq_validator_proposal_assignment_version",
        ),
    )
    op.create_index(
        "ix_validator_proposals_candidate",
        "validator_review_proposals",
        ["candidate_id", "state"],
    )
    op.create_index(
        "ix_validator_proposals_assignment",
        "validator_review_proposals",
        ["assignment_id", "proposal_version"],
    )

    op.create_table(
        "validator_owner_decisions",
        sa.Column("decision_id", sa.String(30), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.String(30),
            sa.ForeignKey("validator_review_proposals.proposal_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "assignment_id",
            sa.String(30),
            sa.ForeignKey("validator_assignments.assignment_id"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(30), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("proposal_hash", sa.String(64), nullable=False),
        sa.Column("owner_notes", sa.Text(), nullable=False),
        sa.Column("decision_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('APPROVE','REQUEST_REVISION','REJECT')",
            name="ck_validator_owner_decision",
        ),
    )
    op.create_index(
        "ix_validator_owner_decisions_owner",
        "validator_owner_decisions",
        ["owner_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("validator_owner_decisions")
    op.drop_table("validator_review_proposals")
    op.drop_index("ix_validator_assignments_decision_owner", table_name="validator_assignments")
    op.drop_constraint(
        "fk_validator_assignments_decision_owner",
        "validator_assignments",
        type_="foreignkey",
    )
    op.drop_column("validator_assignments", "decision_owner_id")
