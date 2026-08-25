"""Post-roadmap Sprint 1: agent lineage and passports.

Revision ID: 0012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_installation_keys",
        sa.Column("installation_key_id", sa.String(30), primary_key=True),
        sa.Column("device_id", sa.String(30), sa.ForeignKey("devices.device_id"),
                  nullable=False, unique=True),
        sa.Column("public_key", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_device_installation_keys_status",
        ),
    )

    op.create_table(
        "agent_genesis",
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), primary_key=True),
        sa.Column("genesis_event_id", sa.String(30), sa.ForeignKey("events.event_id"),
                  nullable=False, unique=True),
        sa.Column("first_device_id", sa.String(30), sa.ForeignKey("devices.device_id"),
                  nullable=False),
        sa.Column("agent_public_key", sa.String(64), nullable=False),
        sa.Column("device_public_key", sa.String(64), nullable=False),
        sa.Column("constitution_hash", sa.String(64), nullable=False),
        sa.Column("born_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "agent_device_authorizations",
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  primary_key=True),
        sa.Column("device_id", sa.String(30), sa.ForeignKey("devices.device_id"),
                  primary_key=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="authorized"),
        sa.Column("assurance_level", sa.String(24), nullable=False, server_default="device"),
        sa.Column("authorized_by_device_id", sa.String(30)),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending', 'authorized', 'revoked', 'recovery_required')",
            name="ck_agent_device_authorizations_status",
        ),
        sa.CheckConstraint(
            "assurance_level IN ('device', 'owner_recovery', 'rotated_key')",
            name="ck_agent_device_authorizations_assurance",
        ),
    )
    op.create_index(
        "ix_agent_device_authorizations_device",
        "agent_device_authorizations",
        ["device_id"],
    )

    op.create_table(
        "enrollment_challenges",
        sa.Column("challenge_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("device_id", sa.String(30), sa.ForeignKey("devices.device_id"),
                  nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False, unique=True),
        sa.Column("constitution_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_enrollment_challenges_agent_device",
        "enrollment_challenges",
        ["agent_id", "device_id"],
    )

    op.create_table(
        "agent_key_rotations",
        sa.Column("rotation_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("device_id", sa.String(30), sa.ForeignKey("devices.device_id"),
                  nullable=False),
        sa.Column("old_public_key", sa.String(64), nullable=False),
        sa.Column("new_public_key", sa.String(64), nullable=False),
        sa.Column("rotation_event_id", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "new_public_key", name="uq_agent_rotation_new_key"),
    )
    op.create_index("ix_agent_key_rotations_agent", "agent_key_rotations", ["agent_id"])

    op.create_table(
        "passport_sessions",
        sa.Column("passport_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("device_id", sa.String(30), sa.ForeignKey("devices.device_id"),
                  nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("nonce_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("constitution_hash", sa.String(64), nullable=False),
        sa.Column("scopes", JSONB, nullable=False, server_default="[]"),
        sa.Column("assurance_level", sa.String(24), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_passport_sessions_agent_device",
        "passport_sessions",
        ["agent_id", "device_id"],
    )

    # Existing agents already have `agent.registered` events and devices. Backfill
    # lineage from public AGORA state only; never infer or store hardware identity.
    op.execute(
        """
        INSERT INTO agent_device_authorizations
            (agent_id, device_id, status, assurance_level, authorized_by_device_id,
             authorized_at, revoked_at)
        SELECT d.agent_id, d.device_id,
               CASE WHEN d.status = 'revoked' THEN 'revoked' ELSE 'authorized' END,
               'device',
               NULL,
               d.created_at,
               d.revoked_at
        FROM devices d
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO agent_genesis
            (agent_id, genesis_event_id, first_device_id, agent_public_key,
             device_public_key, constitution_hash, born_at)
        SELECT DISTINCT ON (a.agent_id)
            a.agent_id,
            e.event_id,
            d.device_id,
            d.public_key,
            d.public_key,
            'd5d7d6f662b9cf5dbb862472c22342f115e39e3c8547787ff91c17db324d90a8',
            COALESCE(e.occurred_at, a.created_at)
        FROM agents a
        JOIN devices d ON d.agent_id = a.agent_id
        JOIN events e ON e.event_type = 'agent.registered'
          AND e.actor->>'agent_id' = a.agent_id
        ORDER BY a.agent_id, d.created_at, e.occurred_at
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_passport_sessions_agent_device", table_name="passport_sessions")
    op.drop_table("passport_sessions")
    op.drop_index("ix_agent_key_rotations_agent", table_name="agent_key_rotations")
    op.drop_table("agent_key_rotations")
    op.drop_index("ix_enrollment_challenges_agent_device", table_name="enrollment_challenges")
    op.drop_table("enrollment_challenges")
    op.drop_index(
        "ix_agent_device_authorizations_device",
        table_name="agent_device_authorizations",
    )
    op.drop_table("agent_device_authorizations")
    op.drop_table("agent_genesis")
    op.drop_table("device_installation_keys")
