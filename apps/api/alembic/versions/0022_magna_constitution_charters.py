"""MAGNA Sprint 1 constitution, charters and rule receipts.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "root_constitutions",
        sa.Column("constitution_id", sa.String(length=30), primary_key=True),
        sa.Column("version", sa.String(length=32), nullable=False, unique=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("issuer_key_id", sa.String(length=128), nullable=False),
        sa.Column("signature", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('draft','active','superseded','revoked')",
            name="ck_root_constitutions_state",
        ),
    )
    op.create_index("ix_root_constitutions_state", "root_constitutions", ["state"])

    op.create_table(
        "world_charters",
        sa.Column("charter_id", sa.String(length=30), primary_key=True),
        sa.Column("world_id", sa.String(length=40), nullable=False),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("charter_version", sa.String(length=32), nullable=False),
        sa.Column("constitution_hash", sa.String(length=64), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("issuer_key_id", sa.String(length=128), nullable=False),
        sa.Column("signatures", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("activation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sunset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_version_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('proposed','active','superseded','rejected','sunset')",
            name="ck_world_charters_state",
        ),
        sa.UniqueConstraint(
            "world_instance_id", "world_id", "charter_version", name="uq_world_charter_version"
        ),
    )
    op.create_index("ix_world_charters_world_state", "world_charters", ["world_id", "state"])

    op.create_table(
        "charter_proposals",
        sa.Column("proposal_id", sa.String(length=30), primary_key=True),
        sa.Column("world_id", sa.String(length=40), nullable=False),
        sa.Column(
            "proposed_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("proposed_by_agent_version_id", sa.String(length=30), nullable=True),
        sa.Column("proposal_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed','rejected','accepted','withdrawn')",
            name="ck_charter_proposals_status",
        ),
    )
    op.create_index(
        "ix_charter_proposals_world_status", "charter_proposals", ["world_id", "status"]
    )

    op.create_table(
        "agent_charter_acceptances",
        sa.Column("acceptance_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "charter_id",
            sa.String(length=30),
            sa.ForeignKey("world_charters.charter_id"),
            nullable=False,
        ),
        sa.Column("world_id", sa.String(length=40), nullable=False),
        sa.Column("charter_version", sa.String(length=32), nullable=False),
        sa.Column("charter_hash", sa.String(length=64), nullable=False),
        sa.Column("constitution_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "agent_id", sa.String(length=30), sa.ForeignKey("agents.agent_id"), nullable=False
        ),
        sa.Column("agent_version_id", sa.String(length=30), nullable=True),
        sa.Column(
            "device_id", sa.String(length=30), sa.ForeignKey("devices.device_id"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "charter_id", name="uq_agent_charter_acceptance"),
        sa.UniqueConstraint("agent_id", "idempotency_key", name="uq_agent_charter_acceptance_idem"),
    )

    op.create_table(
        "rule_evaluation_receipts",
        sa.Column("receipt_id", sa.String(length=64), primary_key=True),
        sa.Column("agent_id", sa.String(length=30), nullable=True),
        sa.Column("world_id", sa.String(length=40), nullable=True),
        sa.Column("requested_action", sa.String(length=80), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("constitution_hash", sa.String(length=64), nullable=False),
        sa.Column("charter_hash", sa.String(length=64), nullable=True),
        sa.Column("output_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ("
            "'allow','deny','require_human_gate','require_more_evidence','stale_rules'"
            ")",
            name="ck_rule_evaluation_decision",
        ),
    )
    op.create_index(
        "ix_rule_eval_agent_action", "rule_evaluation_receipts", ["agent_id", "requested_action"]
    )

    op.create_table(
        "research_release_simulations",
        sa.Column("simulation_id", sa.String(length=64), primary_key=True),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("epoch_id", sa.String(length=96), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("selected_candidate_id", sa.String(length=64), nullable=True),
        sa.Column("reservation_receipt_id", sa.String(length=128), nullable=True),
        sa.Column("result_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("simulated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('RELEASED_ACTIVE','NO_ELIGIBLE_CANDIDATE','REJECTED','CLOSED_NONVIABLE')",
            name="ck_research_release_outcome",
        ),
        sa.UniqueConstraint(
            "world_instance_id", "epoch_id", "input_hash", name="uq_research_release_epoch_input"
        ),
    )
    op.create_index(
        "ix_research_release_epoch",
        "research_release_simulations",
        ["world_instance_id", "epoch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_release_epoch", table_name="research_release_simulations")
    op.drop_table("research_release_simulations")
    op.drop_index("ix_rule_eval_agent_action", table_name="rule_evaluation_receipts")
    op.drop_table("rule_evaluation_receipts")
    op.drop_table("agent_charter_acceptances")
    op.drop_index("ix_charter_proposals_world_status", table_name="charter_proposals")
    op.drop_table("charter_proposals")
    op.drop_index("ix_world_charters_world_state", table_name="world_charters")
    op.drop_table("world_charters")
    op.drop_index("ix_root_constitutions_state", table_name="root_constitutions")
    op.drop_table("root_constitutions")
