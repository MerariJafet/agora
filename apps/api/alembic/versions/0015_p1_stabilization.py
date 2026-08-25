"""P1 stabilization: provenance envelope and challenge action metadata.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROVENANCE_CLASSES = ("real", "demo", "test", "unknown")


def upgrade() -> None:
    op.create_table(
        "record_provenance",
        sa.Column("record_table", sa.String(64), primary_key=True),
        sa.Column("record_id", sa.String(96), primary_key=True),
        sa.Column("environment_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("provenance_class", sa.String(16), nullable=False),
        sa.Column("created_by_actor_or_process", sa.String(128), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provenance_class IN ('real','demo','test','unknown')",
            name="ck_record_provenance_class",
        ),
    )
    op.create_index(
        "ix_record_provenance_class",
        "record_provenance",
        ["provenance_class", "record_table"],
    )
    op.create_index(
        "ix_record_provenance_run",
        "record_provenance",
        ["environment_id", "run_id"],
    )
    op.create_table(
        "record_provenance_audit",
        sa.Column("audit_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("record_table", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(96), nullable=False),
        sa.Column("previous_class", sa.String(16), nullable=True),
        sa.Column("new_class", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "new_class IN ('real','demo','test','unknown')",
            name="ck_record_provenance_audit_class",
        ),
    )
    op.create_index(
        "ix_record_provenance_audit_record",
        "record_provenance_audit",
        ["record_table", "record_id"],
    )

    op.add_column(
        "mission_challenge_submissions",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.add_column(
        "mission_challenge_submissions",
        sa.Column("claim_ids", JSONB, nullable=True),
    )
    op.add_column(
        "mission_challenge_submissions",
        sa.Column("artifact_version_ids", JSONB, nullable=True),
    )
    op.add_column(
        "mission_challenge_submissions",
        sa.Column("evidence_ids", JSONB, nullable=True),
    )
    op.add_column(
        "mission_challenge_submissions",
        sa.Column("limitations", sa.Text(), nullable=True),
    )
    op.add_column(
        "mission_challenge_submissions",
        sa.Column("public_rationale", sa.Text(), nullable=True),
    )
    op.add_column(
        "mission_challenge_votes",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.add_column(
        "mission_challenge_votes",
        sa.Column("verdict", sa.String(16), nullable=True),
    )
    op.add_column(
        "mission_challenge_votes",
        sa.Column("review_evidence_ids", JSONB, nullable=True),
    )
    op.add_column(
        "mission_challenge_votes",
        sa.Column("conflict_of_interest_declaration", sa.Text(), nullable=True),
    )
    op.add_column(
        "mission_challenge_votes",
        sa.Column("abstained", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_unique_constraint(
        "uq_mission_challenge_submission_idempotency",
        "mission_challenge_submissions",
        ["mission_id", "agent_id", "idempotency_key"],
    )
    op.create_unique_constraint(
        "uq_mission_challenge_vote_idempotency",
        "mission_challenge_votes",
        ["submission_id", "voter_agent_id", "idempotency_key"],
    )

    # Authoritative but conservative bootstrap: legacy provenance is unknown.
    legacy_sources = [
        ("agents", "agent_id"),
        ("devices", "device_id"),
        ("spaces", "space_id"),
        ("missions", "mission_id"),
        ("space_messages", "message_id"),
        ("events", "event_id"),
        ("tokoin_ledger_entries", "entry_id"),
        ("mission_challenge_submissions", "submission_id"),
    ]
    for table, column in legacy_sources:
        op.execute(
            sa.text(
                f"""
                INSERT INTO record_provenance (
                    record_table, record_id, environment_id, run_id, provenance_class,
                    created_by_actor_or_process, source_reference, schema_version, created_at
                )
                SELECT :table_name, {column}, 'legacy', 'pre-p1-stabilization',
                       'unknown', 'migration:0015_p1_stabilization',
                       'legacy row existed before authoritative provenance envelope',
                       '1.0', now()
                FROM {table}
                ON CONFLICT (record_table, record_id) DO NOTHING
                """
            ).bindparams(table_name=table)
        )
    op.execute(
        """
        INSERT INTO record_provenance (
            record_table, record_id, environment_id, run_id, provenance_class,
            created_by_actor_or_process, source_reference, schema_version, created_at
        )
        SELECT 'mission_participants', mission_id || '|' || agent_id, 'legacy',
               'pre-p1-stabilization', 'unknown', 'migration:0015_p1_stabilization',
               'legacy row existed before authoritative provenance envelope', '1.0', now()
        FROM mission_participants
        ON CONFLICT (record_table, record_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO record_provenance (
            record_table, record_id, environment_id, run_id, provenance_class,
            created_by_actor_or_process, source_reference, schema_version, created_at
        )
        SELECT 'mission_challenge_votes', submission_id || '|' || voter_agent_id, 'legacy',
               'pre-p1-stabilization', 'unknown', 'migration:0015_p1_stabilization',
               'legacy row existed before authoritative provenance envelope', '1.0', now()
        FROM mission_challenge_votes
        ON CONFLICT (record_table, record_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_mission_challenge_vote_idempotency",
        "mission_challenge_votes",
        type_="unique",
    )
    op.drop_constraint(
        "uq_mission_challenge_submission_idempotency",
        "mission_challenge_submissions",
        type_="unique",
    )
    for column in [
        "abstained",
        "conflict_of_interest_declaration",
        "review_evidence_ids",
        "verdict",
        "idempotency_key",
    ]:
        op.drop_column("mission_challenge_votes", column)
    for column in [
        "public_rationale",
        "limitations",
        "evidence_ids",
        "artifact_version_ids",
        "claim_ids",
        "idempotency_key",
    ]:
        op.drop_column("mission_challenge_submissions", column)
    op.drop_index("ix_record_provenance_audit_record", table_name="record_provenance_audit")
    op.drop_table("record_provenance_audit")
    op.drop_index("ix_record_provenance_run", table_name="record_provenance")
    op.drop_index("ix_record_provenance_class", table_name="record_provenance")
    op.drop_table("record_provenance")
