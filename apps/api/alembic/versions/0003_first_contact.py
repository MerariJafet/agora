"""Sprint 02 First Contact: users, ownership, spaces (+Central Plaza seed),
space_messages, processed_events (durable dedup), claim_challenges,
web_sessions, a2a_tasks.

Revision ID: 0003
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Deterministic well-known id so every environment shares the same plaza.
CENTRAL_PLAZA_ID = "spc_00000000000000000000P1AZA0"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(30), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "agents",
        sa.Column("owner_id", sa.String(30), sa.ForeignKey("users.user_id"), nullable=True),
    )
    op.create_table(
        "web_sessions",
        sa.Column("session_id", sa.String(30), primary_key=True),
        sa.Column("user_id", sa.String(30), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "claim_challenges",
        sa.Column("claim_id", sa.String(30), primary_key=True),
        sa.Column("user_id", sa.String(30), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "spaces",
        sa.Column("space_id", sa.String(30), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="plaza"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        f"""
        INSERT INTO spaces (space_id, slug, name, kind, description, created_at)
        VALUES (
            '{CENTRAL_PLAZA_ID}', 'central-plaza', 'Central Plaza', 'plaza',
            'The founding public square of AGORA. Every agent''s first step.',
            NOW()
        )
        """
    )
    op.create_table(
        "space_messages",
        sa.Column("message_id", sa.String(30), primary_key=True),
        sa.Column("space_id", sa.String(30), sa.ForeignKey("spaces.space_id"), nullable=False),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("agent_version_id", sa.String(30), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("reply_to", sa.String(30), nullable=True),
        sa.Column("event_id", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_space_created", "space_messages", ["space_id", "message_id"])
    op.create_table(
        "processed_events",
        sa.Column("consumer_name", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "a2a_tasks",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("context_id", sa.String(64), nullable=False),
        sa.Column("initiator_agent_id", sa.String(30), nullable=False),
        sa.Column("target_agent_id", sa.String(30), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="submitted"),
        sa.Column("message", JSONB, nullable=False),
        sa.Column("artifacts", JSONB, nullable=True),
        sa.Column("nonce", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_a2a_tasks_target_status", "a2a_tasks", ["target_agent_id", "status"])


def downgrade() -> None:
    for table in ("a2a_tasks", "processed_events", "space_messages", "spaces",
                  "claim_challenges", "web_sessions"):
        op.drop_table(table)
    op.drop_column("agents", "owner_id")
    op.drop_table("users")
