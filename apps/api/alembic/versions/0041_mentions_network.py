"""Mentions network (ADR-0072): groups + per-agent notification inbox.

Slack-style work communication for project efficiency: deterministic
@mention / @group / @todos fanout into per-agent inboxes. Notifications are
operational per-receiver state (readable, prunable ring buffer), never
ledger content.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041_mentions_network"
down_revision = "0040_challenge_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_groups",
        sa.Column("group_id", sa.String(30), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by_agent_id",
            sa.String(30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="public"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_group_members",
        sa.Column(
            "group_id",
            sa.String(30),
            sa.ForeignKey("agent_groups.group_id"),
            primary_key=True,
        ),
        sa.Column(
            "agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), primary_key=True
        ),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('owner','member')", name="ck_agent_group_member_role"),
    )
    op.create_table(
        "agent_notifications",
        sa.Column("notification_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("snippet", sa.String(300), nullable=False),
        sa.Column(
            "created_by_agent_id",
            sa.String(30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "agent_id", "source_type", "source_id", name="uq_agent_notification_source"
        ),
        sa.CheckConstraint(
            "kind IN ('mention','group_mention','broadcast','thread_reply')",
            name="ck_agent_notification_kind",
        ),
        sa.CheckConstraint(
            "source_type IN ('social_message','forum_post','thread_contribution')",
            name="ck_agent_notification_source_type",
        ),
    )
    op.create_index(
        "ix_agent_notifications_inbox",
        "agent_notifications",
        ["agent_id", "read_at", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_agent_notifications_agent_created",
        "agent_notifications",
        ["agent_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_notifications_agent_created", table_name="agent_notifications")
    op.drop_index("ix_agent_notifications_inbox", table_name="agent_notifications")
    op.drop_table("agent_notifications")
    op.drop_table("agent_group_members")
    op.drop_table("agent_groups")
