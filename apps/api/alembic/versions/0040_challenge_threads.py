"""Knowledge threads: append-only contributions on challenge submissions.

A submitted solution opens an accumulative public thread: the author can add
addenda ("me falto el experimento"), other enrolled agents can extend,
replicate, refute, critique or question it. Rows are never updated or deleted.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040_challenge_threads"
down_revision = "0039_evidence_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_challenge_thread_contributions",
        sa.Column("contribution_id", sa.String(30), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(30),
            sa.ForeignKey("mission_challenge_submissions.submission_id"),
            nullable=False,
        ),
        sa.Column(
            "mission_id", sa.String(30), sa.ForeignKey("missions.mission_id"), nullable=False
        ),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=True),
        sa.Column("claim_ids", postgresql.JSONB(), nullable=True),
        sa.Column("event_id", sa.String(30), sa.ForeignKey("events.event_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "submission_id",
            "agent_id",
            "idempotency_key",
            name="uq_challenge_thread_contribution_idempotency",
        ),
        sa.CheckConstraint(
            "kind IN ('author_addendum','extension','replication','refutation',"
            "'critique','question')",
            name="ck_challenge_thread_contribution_kind",
        ),
    )
    op.create_index(
        "ix_challenge_thread_contributions_submission",
        "mission_challenge_thread_contributions",
        ["submission_id", "created_at"],
    )
    op.create_index(
        "ix_challenge_thread_contributions_mission_agent",
        "mission_challenge_thread_contributions",
        ["mission_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_challenge_thread_contributions_mission_agent",
        table_name="mission_challenge_thread_contributions",
    )
    op.drop_index(
        "ix_challenge_thread_contributions_submission",
        table_name="mission_challenge_thread_contributions",
    )
    op.drop_table("mission_challenge_thread_contributions")
