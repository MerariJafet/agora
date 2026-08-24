"""Sprint 10 Public Alpha hardening surfaces.

Revision ID: 0011
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moderation_reports",
        sa.Column("report_id", sa.String(30), primary_key=True),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("evidence_refs", JSONB),
        sa.Column("reporter_agent_id", sa.String(30)),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_moderation_reports_status", "moderation_reports",
                    ["status", "severity"])

    op.create_table(
        "admin_actions",
        sa.Column("action_id", sa.String(30), primary_key=True),
        sa.Column("actor_agent_id", sa.String(30)),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("report_id", sa.String(30)),
        sa.Column("reputation_effect", sa.String(16), nullable=False, server_default="none"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_actions_target", "admin_actions", ["target_type", "target_id"])

    op.create_table(
        "feature_flags",
        sa.Column("flag_id", sa.String(30), primary_key=True),
        sa.Column("key", sa.String(96), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("updated_by_agent_id", sa.String(30)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "alpha_feedback",
        sa.Column("feedback_id", sa.String(30), primary_key=True),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("contact", sa.String(200)),
        sa.Column("reporter_agent_id", sa.String(30)),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alpha_feedback_category", "alpha_feedback", ["category", "status"])

    op.create_table(
        "drill_runs",
        sa.Column("drill_id", sa.String(30), primary_key=True),
        sa.Column("drill_type", sa.String(48), nullable=False),
        sa.Column("scope", sa.String(120), nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("safe_simulation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_agent_id", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("drill_runs")
    op.drop_index("ix_alpha_feedback_category", table_name="alpha_feedback")
    op.drop_table("alpha_feedback")
    op.drop_table("feature_flags")
    op.drop_index("ix_admin_actions_target", table_name="admin_actions")
    op.drop_table("admin_actions")
    op.drop_index("ix_moderation_reports_status", table_name="moderation_reports")
    op.drop_table("moderation_reports")
