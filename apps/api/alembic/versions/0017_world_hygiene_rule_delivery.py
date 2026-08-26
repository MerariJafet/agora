"""World data hygiene and durable rule delivery.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "record_provenance",
        sa.Column("world_instance_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "record_provenance",
        sa.Column("created_by_actor_id", sa.String(30), nullable=True),
    )
    op.add_column(
        "record_provenance",
        sa.Column("created_by_actor_provenance", sa.String(16), nullable=True),
    )
    op.execute(
        """
        UPDATE record_provenance
        SET world_instance_id = CASE provenance_class
            WHEN 'real' THEN 'agora-local-real'
            WHEN 'demo' THEN 'agora-demo'
            WHEN 'test' THEN 'agora-test'
            ELSE 'legacy'
        END
        WHERE world_instance_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE record_provenance
        SET provenance_class = 'real',
            world_instance_id = 'agora-local-real',
            environment_id = CASE
                WHEN environment_id = 'legacy' THEN 'local-dev'
                ELSE environment_id
            END,
            run_id = CASE
                WHEN run_id = 'pre-p1-stabilization' THEN 'canonical-world-seed'
                ELSE run_id
            END
        WHERE (
            record_table = 'spaces'
            AND record_id IN (
                'spc_00000000000000000000P1AZA0',
                'spc_0000000000000000000SCIENCE',
                'spc_0000000000000000000ECONOMY',
                'spc_00000000000000000000GARDEN',
                'spc_000000000000000000000FORGE',
                'spc_0000000000000000000UNKNOWN',
                'spc_00000000000000000000PULSE',
                'spc_000000000000000000000ARENA',
                'spc_000000000000000000FRONTIER',
                'spc_000000000000000000C011ATZ0'
            )
        ) OR (
            record_table = 'missions'
            AND record_id = 'mis_000000000000000000C011ATZ0'
        )
        """
    )
    op.alter_column("record_provenance", "world_instance_id", nullable=False)
    op.create_index(
        "ix_record_provenance_world",
        "record_provenance",
        ["world_instance_id", "provenance_class"],
    )
    op.create_table(
        "record_quarantine",
        sa.Column("quarantine_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("record_table", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(96), nullable=False),
        sa.Column("reason", sa.String(96), nullable=False),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("invalidated_state", JSONB, nullable=True),
        sa.Column("created_by_actor_or_process", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("record_table", "record_id", "reason", name="uq_record_quarantine"),
    )
    op.create_index(
        "ix_record_quarantine_record", "record_quarantine", ["record_table", "record_id"]
    )
    op.execute(
        """
        INSERT INTO record_quarantine (
            record_table, record_id, reason, evidence_reference, invalidated_state,
            created_by_actor_or_process, created_at
        )
        SELECT
            'mission_participants',
            mp.mission_id || '|' || mp.agent_id,
            'INVALIDATED_PRE_START_CONTAMINATION',
            'docs/work/world-data-hygiene-root-cause-audit.md#phase-0',
            jsonb_build_object(
                'mission_id', mp.mission_id,
                'agent_id', mp.agent_id,
                'agent_name', a.name,
                'participant_provenance', pr.provenance_class,
                'actor_provenance', apr.provenance_class
            ),
            'migration:0017_world_hygiene_rule_delivery',
            now()
        FROM mission_participants mp
        JOIN agents a ON a.agent_id = mp.agent_id
        JOIN record_provenance pr
          ON pr.record_table = 'mission_participants'
         AND pr.record_id = mp.mission_id || '|' || mp.agent_id
        LEFT JOIN record_provenance apr
          ON apr.record_table = 'agents'
         AND apr.record_id = mp.agent_id
        WHERE mp.mission_id = 'mis_00000000000000000000UNKSIG01'
          AND pr.provenance_class = 'real'
          AND COALESCE(apr.provenance_class, 'unknown') <> 'real'
        ON CONFLICT (record_table, record_id, reason) DO NOTHING
        """
    )
    op.create_table(
        "rule_documents",
        sa.Column("rule_id", sa.String(64), primary_key=True),
        sa.Column("rule_class", sa.String(32), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("world_instance_id", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("canonical_body", JSONB, nullable=False),
        sa.Column("canonical_hash", sa.String(64), nullable=False),
        sa.Column("constitution_hash", sa.String(64), nullable=False),
        sa.Column("issuer_key_id", sa.String(128), nullable=False),
        sa.Column("signature", JSONB, nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("minimum_protocol_version", sa.String(32), nullable=True),
        sa.Column("supersedes_rule_id", sa.String(64), nullable=True),
        sa.Column("required_attestation_type", sa.String(64), nullable=False),
        sa.Column("consequence_if_unattested", sa.Text(), nullable=False),
        sa.Column("appeal_mechanism", sa.Text(), nullable=True),
        sa.Column("rollback_metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "sequence_number", name="uq_rule_sequence_world"),
        sa.CheckConstraint(
            "state IN ('draft','active','superseded','revoked')",
            name="ck_rule_documents_state",
        ),
    )
    op.create_index(
        "ix_rule_documents_world_state", "rule_documents", ["world_instance_id", "state"]
    )
    op.create_table(
        "rule_delivery_states",
        sa.Column(
            "rule_id", sa.String(64), sa.ForeignKey("rule_documents.rule_id"), primary_key=True
        ),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), primary_key=True),
        sa.Column("agent_version_id", sa.String(30), nullable=True),
        sa.Column("device_id", sa.String(30), nullable=True),
        sa.Column("eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("queued", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signature_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compatible_attested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("incompatible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deferred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("technical_state", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("technical_cause", sa.String(128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("cursor_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "technical_state IN ('queued','delivered','seen','compatible','incompatible',"
            "'deferred','declined','failed','protocol_incompatible')",
            name="ck_rule_delivery_state",
        ),
    )
    op.create_index(
        "ix_rule_delivery_agent_state", "rule_delivery_states", ["agent_id", "technical_state"]
    )
    op.create_index(
        "ix_rule_delivery_rule_state", "rule_delivery_states", ["rule_id", "technical_state"]
    )


def downgrade() -> None:
    op.drop_index("ix_rule_delivery_rule_state", table_name="rule_delivery_states")
    op.drop_index("ix_rule_delivery_agent_state", table_name="rule_delivery_states")
    op.drop_table("rule_delivery_states")
    op.drop_index("ix_rule_documents_world_state", table_name="rule_documents")
    op.drop_table("rule_documents")
    op.drop_index("ix_record_quarantine_record", table_name="record_quarantine")
    op.drop_table("record_quarantine")
    op.drop_index("ix_record_provenance_world", table_name="record_provenance")
    op.drop_column("record_provenance", "created_by_actor_provenance")
    op.drop_column("record_provenance", "created_by_actor_id")
    op.drop_column("record_provenance", "world_instance_id")
