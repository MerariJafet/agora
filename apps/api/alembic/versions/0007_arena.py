"""Sprint 06 Arena: challenges, immutable versions, instances,
submissions, judgments, score events and ratings.

Revision ID: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO spaces (space_id, slug, name, kind, description, created_at) "
            "VALUES (:sid, :slug, :name, 'arena', :descr, NOW()) "
            "ON CONFLICT (space_id) DO NOTHING"
        ),
        {
            "sid": "spc_000000000000000000000ARENA",
            "slug": "agora-arena",
            "name": "AGORA Arena",
            "descr": "Competition, Challenges and rankings without treating victory as truth.",
        },
    )

    op.create_table(
        "arena_seasons",
        sa.Column("season_id", sa.String(30), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "arena_challenges",
        sa.Column("challenge_id", sa.String(30), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("current_version_id", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('draft','validating','open','active','judging','resolved','archived')",
            name="ck_arena_challenge_state",
        ),
    )
    op.create_index("ix_arena_challenges_state", "arena_challenges", ["state"])
    op.create_index("ix_arena_challenges_domain", "arena_challenges", ["domain"])

    op.create_table(
        "arena_challenge_versions",
        sa.Column("challenge_version_id", sa.String(30), primary_key=True),
        sa.Column("challenge_id", sa.String(30), sa.ForeignKey("arena_challenges.challenge_id"),
                  nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("complexity", JSONB, nullable=False),
        sa.Column("certified_difficulty", sa.Float, nullable=False),
        sa.Column("verifier_manifest", JSONB, nullable=False),
        sa.Column("scoring_formula", JSONB, nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_arena_challenge_versions_challenge",
        "arena_challenge_versions",
        ["challenge_id", "version_number"],
        unique=True,
    )

    op.create_table(
        "arena_challenge_instances",
        sa.Column("challenge_instance_id", sa.String(30), primary_key=True),
        sa.Column("challenge_id", sa.String(30), sa.ForeignKey("arena_challenges.challenge_id"),
                  nullable=False),
        sa.Column("challenge_version_id", sa.String(30),
                  sa.ForeignKey("arena_challenge_versions.challenge_version_id"),
                  nullable=False),
        sa.Column("season_id", sa.String(30), nullable=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("max_participants", sa.Integer, nullable=False, server_default="16"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("max_participants >= 1", name="ck_arena_instance_participants"),
        sa.CheckConstraint(
            "state IN ('pending','active','judging','resolved','cancelled')",
            name="ck_arena_instance_state",
        ),
    )
    op.create_index("ix_arena_instances_state", "arena_challenge_instances", ["state"])
    op.create_index("ix_arena_instances_challenge", "arena_challenge_instances", ["challenge_id"])

    op.create_table(
        "arena_participants",
        sa.Column("challenge_instance_id", sa.String(30),
                  sa.ForeignKey("arena_challenge_instances.challenge_instance_id"),
                  primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  primary_key=True),
        sa.Column("owner_id", sa.String(30), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "arena_submissions",
        sa.Column("submission_id", sa.String(30), primary_key=True),
        sa.Column("challenge_instance_id", sa.String(30),
                  sa.ForeignKey("arena_challenge_instances.challenge_instance_id"),
                  nullable=False),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("answer", JSONB, nullable=False),
        sa.Column("artifact_version_id", sa.String(30), nullable=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="submitted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("challenge_instance_id", "agent_id",
                            name="uq_arena_submission_agent"),
        sa.CheckConstraint("state IN ('submitted','judged','rejected')",
                           name="ck_arena_submission_state"),
    )
    op.create_index("ix_arena_submissions_instance", "arena_submissions",
                    ["challenge_instance_id"])

    op.create_table(
        "arena_judgments",
        sa.Column("judgment_id", sa.String(30), primary_key=True),
        sa.Column("submission_id", sa.String(30), sa.ForeignKey("arena_submissions.submission_id"),
                  nullable=False),
        sa.Column("judge_kind", sa.String(16), nullable=False),
        sa.Column("judge_agent_id", sa.String(30), nullable=True),
        sa.Column("correctness", sa.Float, nullable=True),
        sa.Column("audience_preference", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("judge_kind IN ('objective','judge','audience')",
                           name="ck_arena_judgment_kind"),
    )
    op.create_index("ix_arena_judgments_submission", "arena_judgments", ["submission_id"])

    op.create_table(
        "arena_score_events",
        sa.Column("score_event_id", sa.String(30), primary_key=True),
        sa.Column("challenge_instance_id", sa.String(30),
                  sa.ForeignKey("arena_challenge_instances.challenge_instance_id"),
                  nullable=False),
        sa.Column("submission_id", sa.String(30), sa.ForeignKey("arena_submissions.submission_id"),
                  nullable=False),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("score_delta", sa.Float, nullable=False),
        sa.Column("rating_delta", sa.Float, nullable=False, server_default="0"),
        sa.Column("formula_version", sa.String(16), nullable=False),
        sa.Column("factors", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("submission_id", name="uq_arena_score_submission"),
    )
    op.create_index("ix_arena_score_events_agent", "arena_score_events", ["agent_id"])
    op.create_index("ix_arena_score_events_instance", "arena_score_events",
                    ["challenge_instance_id"])

    op.create_table(
        "arena_ratings",
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  primary_key=True),
        sa.Column("domain", sa.String(64), primary_key=True),
        sa.Column("rating", sa.Float, nullable=False, server_default="1500"),
        sa.Column("rating_deviation", sa.Float, nullable=False, server_default="350"),
        sa.Column("points", sa.Float, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("arena_ratings")
    op.drop_table("arena_score_events")
    op.drop_table("arena_judgments")
    op.drop_table("arena_submissions")
    op.drop_table("arena_participants")
    op.drop_table("arena_challenge_instances")
    op.drop_table("arena_challenge_versions")
    op.drop_table("arena_challenges")
    op.drop_table("arena_seasons")
    op.execute(
        sa.text("DELETE FROM spaces WHERE space_id = 'spc_000000000000000000000ARENA'")
    )
