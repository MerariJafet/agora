"""Sprint 01 foundation: agents, agent_versions, devices, registration_challenges,
device_sessions, events (append-only ledger), event_outbox, idempotency_records.

Revision ID: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.String(30), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="registered"),
        sa.Column("current_version_id", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_versions",
        sa.Column("agent_version_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_agent_version_number", "agent_versions", ["agent_id", "version"], unique=True
    )
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("public_key", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="authorized"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "registration_challenges",
        sa.Column("challenge_id", sa.String(30), primary_key=True),
        sa.Column("nonce", sa.String(64), nullable=False, unique=True),
        sa.Column("public_key", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "device_sessions",
        sa.Column("session_id", sa.String(30), primary_key=True),
        sa.Column("device_id", sa.String(30), sa.ForeignKey("devices.device_id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("event_id", sa.String(30), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", JSONB, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("causation_id", sa.String(30), nullable=True),
        sa.Column("trace_id", sa.String(32), nullable=True),
        sa.Column("signature", sa.String(128), nullable=True),
    )
    op.create_index("ix_events_type_occurred", "events", ["event_type", "occurred_at"])
    op.create_table(
        "event_outbox",
        sa.Column("outbox_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "event_id",
            sa.String(30),
            sa.ForeignKey("events.event_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("published", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outbox_unpublished", "event_outbox", ["published", "outbox_id"])
    op.create_table(
        "idempotency_records",
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("endpoint", sa.String(64), primary_key=True),
        sa.Column("response_body", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # The event ledger is append-only. Defense in depth: reject UPDATE/DELETE
    # at the database layer, not just by application convention.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION agora_events_immutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'events ledger is append-only (% blocked)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_events_no_update
            BEFORE UPDATE ON events
            FOR EACH ROW EXECUTE FUNCTION agora_events_immutable();

        CREATE TRIGGER trg_events_no_delete
            BEFORE DELETE ON events
            FOR EACH ROW EXECUTE FUNCTION agora_events_immutable();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_events_no_update ON events")
    op.execute("DROP TRIGGER IF EXISTS trg_events_no_delete ON events")
    op.execute("DROP FUNCTION IF EXISTS agora_events_immutable")
    for table in (
        "idempotency_records",
        "event_outbox",
        "events",
        "device_sessions",
        "registration_challenges",
        "devices",
        "agent_versions",
        "agents",
    ):
        op.drop_table(table)
