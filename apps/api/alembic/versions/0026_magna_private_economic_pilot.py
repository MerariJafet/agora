"""MAGNA Sprint 04.4 private economic pilot receipts.

Revision ID: 0026_magna_private
Revises: 0025_magna_tokoin_testnet
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_magna_private"
down_revision = "0025_magna_tokoin_testnet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tokoin_private_pilot_receipts",
        sa.Column("receipt_id", sa.String(30), primary_key=True),
        sa.Column("receipt_type", sa.String(48), nullable=False),
        sa.Column("subject_id", sa.String(120), nullable=False),
        sa.Column("canonical_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "receipt_type IN ('founder_ratification','settlement_authorization',"
            "'settlement_receipt','reconciliation_receipt','wallet_readiness',"
            "'simulation_receipt','backup_restore_receipt')",
            name="ck_tokoin_private_receipt_type",
        ),
        sa.UniqueConstraint(
            "receipt_type", "subject_id", name="uq_tokoin_private_receipt_subject"
        ),
    )
    op.create_index(
        "ix_tokoin_private_receipts_type",
        "tokoin_private_pilot_receipts",
        ["receipt_type"],
    )

    op.create_table(
        "tokoin_devnet_transfers",
        sa.Column("transfer_id", sa.String(30), primary_key=True),
        sa.Column(
            "settlement_plan_id",
            sa.String(30),
            sa.ForeignKey("tokoin_settlement_plans.settlement_plan_id"),
            nullable=False,
        ),
        sa.Column("chain_id", sa.Integer, nullable=False),
        sa.Column("contract_address", sa.String(42), nullable=False),
        sa.Column("tx_hash", sa.String(66), nullable=False, unique=True),
        sa.Column("block_number", sa.Integer, nullable=False),
        sa.Column("transfer_payload", postgresql.JSONB, nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("chain_id = 31337", name="ck_tokoin_devnet_transfer_chain"),
        sa.CheckConstraint(
            "state IN ('broadcast','confirmed','reconciled','stale')",
            name="ck_tokoin_devnet_transfer_state",
        ),
        sa.UniqueConstraint("settlement_plan_id", name="uq_tokoin_devnet_transfer_plan"),
    )
    op.create_index(
        "ix_tokoin_devnet_transfers_state", "tokoin_devnet_transfers", ["state"]
    )

    op.create_table(
        "tokoin_pre_public_reward_entitlements",
        sa.Column("entitlement_id", sa.String(30), primary_key=True),
        sa.Column(
            "settlement_plan_id",
            sa.String(30),
            sa.ForeignKey("tokoin_settlement_plans.settlement_plan_id"),
            nullable=False,
        ),
        sa.Column(
            "allocation_id",
            sa.String(30),
            sa.ForeignKey("tokoin_claimable_allocations.allocation_id"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column(
            "wallet_binding_id",
            sa.String(30),
            sa.ForeignKey("tokoin_wallet_bindings.binding_id"),
            nullable=False,
        ),
        sa.Column("amount_atomic", sa.String(32), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column(
            "source_transfer_id",
            sa.String(30),
            sa.ForeignKey("tokoin_devnet_transfers.transfer_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_atomic ~ '^[0-9]+$'", name="ck_pre_public_amount"),
        sa.CheckConstraint(
            "classification = 'PRE_PUBLIC_EARNED'", name="ck_pre_public_classification"
        ),
        sa.CheckConstraint("state IN ('earned','voided')", name="ck_pre_public_state"),
        sa.UniqueConstraint("allocation_id", name="uq_tokoin_pre_public_allocation"),
    )
    op.create_index(
        "ix_tokoin_pre_public_agent_state",
        "tokoin_pre_public_reward_entitlements",
        ["agent_id", "state"],
    )

    op.create_table(
        "tokoin_migration_snapshots",
        sa.Column("snapshot_id", sa.String(30), primary_key=True),
        sa.Column("snapshot_type", sa.String(32), nullable=False),
        sa.Column("merkle_root", sa.String(64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("total_supply_atomic", sa.String(32), nullable=False),
        sa.Column("treasury_remainder_atomic", sa.String(32), nullable=False),
        sa.Column("claimable_atomic", sa.String(32), nullable=False),
        sa.Column("public_claim_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "snapshot_type IN ('TEST_ONLY_MIGRATION_PREVIEW')",
            name="ck_tokoin_migration_snapshot_type",
        ),
        sa.CheckConstraint(
            "total_supply_atomic = '100000000000000'",
            name="ck_tokoin_migration_snapshot_supply",
        ),
        sa.CheckConstraint(
            "public_claim_enabled = false", name="ck_tokoin_migration_claim_disabled"
        ),
    )
    op.create_index(
        "ix_tokoin_migration_snapshots_type",
        "tokoin_migration_snapshots",
        ["snapshot_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_tokoin_migration_snapshots_type", table_name="tokoin_migration_snapshots")
    op.drop_table("tokoin_migration_snapshots")
    op.drop_index(
        "ix_tokoin_pre_public_agent_state",
        table_name="tokoin_pre_public_reward_entitlements",
    )
    op.drop_table("tokoin_pre_public_reward_entitlements")
    op.drop_index("ix_tokoin_devnet_transfers_state", table_name="tokoin_devnet_transfers")
    op.drop_table("tokoin_devnet_transfers")
    op.drop_index(
        "ix_tokoin_private_receipts_type", table_name="tokoin_private_pilot_receipts"
    )
    op.drop_table("tokoin_private_pilot_receipts")
