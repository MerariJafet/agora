"""Version-scoped research scoring and candidate idempotency.

Revision ID: 0033_research_idempotency
Revises: 0032_research_protocol
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_research_idempotency"
down_revision = "0032_research_protocol"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_candidate_snapshots",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.execute(
        """
        UPDATE research_candidate_snapshots
        SET idempotency_key = 'legacy:' || candidate_id
        WHERE idempotency_key IS NULL
        """
    )
    op.alter_column("research_candidate_snapshots", "idempotency_key", nullable=False)
    op.create_unique_constraint(
        "uq_research_candidate_idempotency",
        "research_candidate_snapshots",
        ["challenge_id", "idempotency_key"],
    )

    op.add_column(
        "research_contribution_scores",
        sa.Column("candidate_id", sa.String(30), nullable=True),
    )
    op.execute(
        """
        UPDATE research_contribution_scores score
        SET candidate_id = (
          SELECT snapshot.candidate_id
          FROM research_candidate_snapshots snapshot
          WHERE snapshot.challenge_id = score.challenge_id
            AND snapshot.created_at <= score.created_at
          ORDER BY snapshot.created_at DESC, snapshot.candidate_version DESC
          LIMIT 1
        )
        WHERE score.candidate_id IS NULL
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM research_contribution_scores WHERE candidate_id IS NULL) THEN
            RAISE EXCEPTION 'research score has no attributable candidate snapshot';
          END IF;
        END $$
        """
    )
    op.alter_column("research_contribution_scores", "candidate_id", nullable=False)
    op.create_foreign_key(
        "fk_research_score_candidate",
        "research_contribution_scores",
        "research_candidate_snapshots",
        ["candidate_id"],
        ["candidate_id"],
    )
    op.drop_constraint(
        "uq_research_score_object_algo", "research_contribution_scores", type_="unique"
    )
    op.create_unique_constraint(
        "uq_research_score_candidate_object_algo",
        "research_contribution_scores",
        ["candidate_id", "object_id", "algorithm_version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_research_score_candidate_object_algo",
        "research_contribution_scores",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_research_score_object_algo",
        "research_contribution_scores",
        ["object_id", "algorithm_version"],
    )
    op.drop_constraint(
        "fk_research_score_candidate", "research_contribution_scores", type_="foreignkey"
    )
    op.drop_column("research_contribution_scores", "candidate_id")
    op.drop_constraint(
        "uq_research_candidate_idempotency", "research_candidate_snapshots", type_="unique"
    )
    op.drop_column("research_candidate_snapshots", "idempotency_key")
