"""P2 world actionability and Unknown Signal experiment.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_identity_metadata",
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), primary_key=True),
        sa.Column("canonical_name", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(96), nullable=True),
        sa.Column("aliases", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("runtime_provider", sa.String(64), nullable=True),
        sa.Column("model_id", sa.String(128), nullable=True),
        sa.Column("runtime_version", sa.String(64), nullable=True),
        sa.Column("metadata_assurance", sa.String(32), nullable=False, server_default="db"),
        sa.Column("metadata_conflict", JSONB, nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "world_experiments",
        sa.Column("experiment_id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("environment_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="registered"),
        sa.Column("cohort_manifest", JSONB, nullable=False),
        sa.Column("cohort_manifest_hash", sa.String(64), nullable=False),
        sa.Column("protocol_manifest", JSONB, nullable=False),
        sa.Column("protocol_manifest_hash", sa.String(64), nullable=False),
        sa.Column("dataset_manifest_hash", sa.String(64), nullable=True),
        sa.Column("sealed_ground_truth_hash", sa.String(64), nullable=True),
        sa.Column("public_instruction_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('registered','open','running','closed','evaluated','cancelled')",
            name="ck_world_experiments_status",
        ),
    )
    op.create_index("ix_world_experiments_run", "world_experiments", ["run_id"])
    op.create_index("ix_world_experiments_status", "world_experiments", ["status"])
    op.create_table(
        "unknown_signal_datasets",
        sa.Column("dataset_id", sa.String(64), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.String(64),
            sa.ForeignKey("world_experiments.experiment_id"),
            nullable=False,
        ),
        sa.Column("seed", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("dataset_manifest", JSONB, nullable=False),
        sa.Column("dataset_manifest_hash", sa.String(64), nullable=False),
        sa.Column("sealed_ground_truth", JSONB, nullable=False),
        sa.Column("sealed_ground_truth_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_count BETWEEN 20000 AND 50000", name="ck_unknown_signal_rows"),
    )
    op.create_index(
        "ix_unknown_signal_experiment", "unknown_signal_datasets", ["experiment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_unknown_signal_experiment", table_name="unknown_signal_datasets")
    op.drop_table("unknown_signal_datasets")
    op.drop_index("ix_world_experiments_status", table_name="world_experiments")
    op.drop_index("ix_world_experiments_run", table_name="world_experiments")
    op.drop_table("world_experiments")
    op.drop_table("agent_identity_metadata")
