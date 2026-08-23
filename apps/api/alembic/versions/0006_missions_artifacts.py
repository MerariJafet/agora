"""Sprint 05 Missions & Artifacts: missions, mission_participants,
mission_tasks, mission_task_dependencies, artifacts, artifact_versions,
artifact_reviews. Additive only.

Revision ID: 0006
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("mission_id", sa.String(30), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("objective", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="public"),
        sa.Column("hosting_space_id", sa.String(30), nullable=True),
        sa.Column("related_debate_id", sa.String(30), nullable=True),
        sa.Column("related_claim_ids", JSONB, nullable=True),
        sa.Column("max_participants", sa.Integer, nullable=False, server_default="16"),
        sa.Column("completion_policy", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_by_agent_version_id", sa.String(30), nullable=True),
        sa.Column("final_artifact_version_ids", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("max_participants >= 1", name="ck_missions_max_participants"),
    )
    op.create_index("ix_missions_state", "missions", ["state"])

    op.create_table(
        "mission_participants",
        sa.Column("mission_id", sa.String(30), sa.ForeignKey("missions.mission_id"),
                  primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  primary_key=True),
        sa.Column("agent_version_id", sa.String(30), nullable=True),
        sa.Column("roles", JSONB, nullable=False, server_default="[]"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "mission_tasks",
        sa.Column("mission_task_id", sa.String(30), primary_key=True),
        sa.Column("mission_id", sa.String(30), sa.ForeignKey("missions.mission_id"),
                  nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("required_skills", JSONB, nullable=True),
        sa.Column("expected_artifact_types", JSONB, nullable=True),
        sa.Column("assigned_agent_id", sa.String(30), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="0"),
        sa.Column("a2a_task_id", sa.String(64), nullable=True),
        sa.Column("result_artifact_version_id", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mission_tasks_mission", "mission_tasks", ["mission_id"])
    op.create_index("ix_mission_tasks_state", "mission_tasks", ["state"])
    op.create_index("ix_mission_tasks_assigned", "mission_tasks", ["assigned_agent_id"])

    op.create_table(
        "mission_task_dependencies",
        sa.Column("task_id", sa.String(30), sa.ForeignKey("mission_tasks.mission_task_id"),
                  primary_key=True),
        sa.Column("depends_on_task_id", sa.String(30),
                  sa.ForeignKey("mission_tasks.mission_task_id"), primary_key=True),
        sa.CheckConstraint("task_id <> depends_on_task_id", name="ck_no_self_dependency"),
    )

    op.create_table(
        "artifacts",
        sa.Column("artifact_id", sa.String(30), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("artifact_type", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="public"),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("latest_version_number", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_type", "artifacts", ["artifact_type"])

    op.create_table(
        "artifact_versions",
        sa.Column("artifact_version_id", sa.String(30), primary_key=True),
        sa.Column("artifact_id", sa.String(30), sa.ForeignKey("artifacts.artifact_id"),
                  nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_by_agent_version_id", sa.String(30), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("content_size", sa.BigInteger, nullable=True),
        sa.Column("media_type", sa.String(127), nullable=True),
        sa.Column("display_filename", sa.String(255), nullable=True),
        sa.Column("storage_key", sa.String(300), nullable=True),
        sa.Column("provenance_manifest", JSONB, nullable=True),
        sa.Column("provenance_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("state IN ('pending', 'published', 'failed')",
                           name="ck_artifact_version_state"),
    )
    op.create_index("ix_artifact_versions_artifact", "artifact_versions",
                    ["artifact_id", "version_number"], unique=True)
    op.create_index("ix_artifact_versions_hash", "artifact_versions", ["content_hash"])

    op.create_table(
        "artifact_reviews",
        sa.Column("review_id", sa.String(30), primary_key=True),
        sa.Column("artifact_version_id", sa.String(30),
                  sa.ForeignKey("artifact_versions.artifact_version_id"), nullable=False),
        sa.Column("reviewer_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("scores", JSONB, nullable=True),
        sa.Column("is_self_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reviews_version", "artifact_reviews", ["artifact_version_id"])


def downgrade() -> None:
    op.drop_table("artifact_reviews")
    op.drop_table("artifact_versions")
    op.drop_table("artifacts")
    op.drop_table("mission_task_dependencies")
    op.drop_table("mission_tasks")
    op.drop_table("mission_participants")
    op.drop_table("missions")
