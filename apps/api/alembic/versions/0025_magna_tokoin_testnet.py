"""MAGNA Sprint 04 TOKOIN local-devnet/testnet control plane.

Revision ID: 0025_magna_tokoin_testnet
Revises: 0024_magna_knowledge_ledger
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025_magna_tokoin_testnet"
down_revision = "0024_magna_knowledge_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_magna_object_state", "magna_knowledge_objects", type_="check")
    op.create_check_constraint(
        "ck_magna_object_state",
        "magna_knowledge_objects",
        "state IN ('PROPOSED','UNDER_TEST','SUPPORTED_ONCE','REPLICATED',"
        "'RESOLVED_VERIFIED','CONTESTED','REFUTED','INCONCLUSIVE','SUPERSEDED')",
    )
    op.drop_constraint("ck_magna_receipt_state", "magna_resolution_receipts", type_="check")
    op.create_check_constraint(
        "ck_magna_receipt_state",
        "magna_resolution_receipts",
        "requested_state IN ('PROPOSED','UNDER_TEST','SUPPORTED_ONCE','REPLICATED',"
        "'RESOLVED_VERIFIED','CONTESTED','REFUTED','INCONCLUSIVE','SUPERSEDED')",
    )

    op.create_table(
        "tokoin_deployment_manifests",
        sa.Column("deployment_id", sa.String(30), primary_key=True),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("network_key", sa.String(40), nullable=False),
        sa.Column("chain_id", sa.Integer, nullable=False),
        sa.Column("token_address", sa.String(42), nullable=False),
        sa.Column("genesis_treasury_address", sa.String(42), nullable=False),
        sa.Column("reward_budget_vault_address", sa.String(42), nullable=False),
        sa.Column("challenge_escrow_address", sa.String(42), nullable=False),
        sa.Column("reward_splitter_address", sa.String(42), nullable=False),
        sa.Column("pool_escrow_address", sa.String(42), nullable=False),
        sa.Column("agent_passport_anchor_address", sa.String(42), nullable=False),
        sa.Column("knowledge_root_registry_address", sa.String(42), nullable=False),
        sa.Column("total_supply_atomic", sa.String(32), nullable=False),
        sa.Column("decimals", sa.Integer, nullable=False),
        sa.Column("solidity_version", sa.String(32), nullable=False),
        sa.Column("openzeppelin_version", sa.String(32), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("bytecode_verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("human_ratifications", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decimals = 8", name="ck_tokoin_manifest_decimals"),
        sa.CheckConstraint(
            "total_supply_atomic = '100000000000000'",
            name="ck_tokoin_manifest_fixed_supply",
        ),
        sa.CheckConstraint("chain_id IN (31337, 84532)", name="ck_tokoin_manifest_chain_allowlist"),
        sa.UniqueConstraint("network_key", "chain_id", name="uq_tokoin_deployment_network"),
    )
    op.create_index(
        "ix_tokoin_deployments_status", "tokoin_deployment_manifests", ["status"]
    )

    op.create_table(
        "tokoin_wallet_bindings",
        sa.Column("binding_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=True),
        sa.Column("controller_commitment_hash", sa.String(64), nullable=False),
        sa.Column("wallet_address", sa.String(42), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("chain_id", sa.Integer, nullable=False),
        sa.Column("balance_cache_atomic", sa.String(32), nullable=False, server_default="0"),
        sa.Column("session_policy", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("rotation_receipt", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("chain_id IN (31337, 84532)", name="ck_tokoin_wallet_chain_allowlist"),
        sa.CheckConstraint(
            "state IN ('PENDING_ADMISSION','TESTNET_RECEIVE_ONLY','TESTNET_LIMITED_SESSION',"
            "'SUSPENDED','ROTATION_PENDING','REVOKED')",
            name="ck_tokoin_wallet_state",
        ),
        sa.CheckConstraint("balance_cache_atomic ~ '^[0-9]+$'", name="ck_tokoin_wallet_amount"),
        sa.UniqueConstraint("agent_id", "chain_id", name="uq_tokoin_wallet_binding_agent_chain"),
        sa.UniqueConstraint(
            "wallet_address", "chain_id", name="uq_tokoin_wallet_binding_address"
        ),
    )
    op.create_index("ix_tokoin_wallet_bindings_state", "tokoin_wallet_bindings", ["state"])

    op.create_table(
        "tokoin_reservations",
        sa.Column("reservation_id", sa.String(30), primary_key=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("world_instance_id", sa.String(64), nullable=False),
        sa.Column("challenge_id", sa.String(80), nullable=False),
        sa.Column("candidate_id", sa.String(80), nullable=False),
        sa.Column("settlement_backend", sa.String(40), nullable=False),
        sa.Column("chain_id", sa.Integer, nullable=False),
        sa.Column("escrow_address", sa.String(42), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("amount_atomic", sa.String(32), nullable=False),
        sa.Column("tx_hash", sa.String(66), nullable=True),
        sa.Column("finality_evidence", postgresql.JSONB, nullable=True),
        sa.Column(
            "resolution_receipt_id",
            sa.String(30),
            sa.ForeignKey("magna_resolution_receipts.receipt_id"),
            nullable=True,
        ),
        sa.Column("settlement_plan_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("chain_id IN (31337, 84532)", name="ck_tokoin_reservation_chain"),
        sa.CheckConstraint("amount_atomic = '100000000'", name="ck_tokoin_reservation_one"),
        sa.CheckConstraint(
            "settlement_backend IN ('TOKOIN_LOCAL_DEVNET_V1','TOKOIN_BASE_SEPOLIA_TESTNET_V1')",
            name="ck_tokoin_reservation_backend",
        ),
        sa.CheckConstraint(
            "state IN ('RESERVATION_REQUESTED','ONCHAIN_SUBMITTED','ONCHAIN_PENDING',"
            "'FINALITY_CONFIRMED','RESERVED','RELEASED_ACTIVE','FAILED_PRE_SUBMISSION',"
            "'FAILED_ONCHAIN','REORG_DETECTED','EXPIRED','CANCELLED','RECONCILIATION_REQUIRED')",
            name="ck_tokoin_reservation_state",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_tokoin_reservation_idempotency"),
        sa.UniqueConstraint(
            "world_instance_id", "challenge_id", name="uq_tokoin_reservation_challenge"
        ),
    )
    op.create_index("ix_tokoin_reservations_state", "tokoin_reservations", ["state"])

    op.create_table(
        "tokoin_settlement_plans",
        sa.Column("settlement_plan_id", sa.String(30), primary_key=True),
        sa.Column("challenge_id", sa.String(80), nullable=False),
        sa.Column(
            "reservation_id",
            sa.String(30),
            sa.ForeignKey("tokoin_reservations.reservation_id"),
            nullable=False,
        ),
        sa.Column(
            "resolution_receipt_id",
            sa.String(30),
            sa.ForeignKey("magna_resolution_receipts.receipt_id"),
            nullable=False,
        ),
        sa.Column("plan_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("total_atomic", sa.String(32), nullable=False),
        sa.Column("role_allocations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("unused_return_atomic", sa.String(32), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("total_atomic = '100000000'", name="ck_tokoin_settlement_total"),
        sa.CheckConstraint("unused_return_atomic ~ '^[0-9]+$'", name="ck_tokoin_settlement_unused"),
        sa.CheckConstraint(
            "state IN ('DRAFT','AUTHORIZED','ALLOCATED','SETTLED','CANCELLED')",
            name="ck_tokoin_settlement_state",
        ),
        sa.UniqueConstraint("challenge_id", name="uq_tokoin_settlement_plan_challenge"),
    )
    op.create_index("ix_tokoin_settlement_plans_state", "tokoin_settlement_plans", ["state"])

    op.create_table(
        "tokoin_claimable_allocations",
        sa.Column("allocation_id", sa.String(30), primary_key=True),
        sa.Column(
            "settlement_plan_id",
            sa.String(30),
            sa.ForeignKey("tokoin_settlement_plans.settlement_plan_id"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column(
            "wallet_binding_id",
            sa.String(30),
            sa.ForeignKey("tokoin_wallet_bindings.binding_id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("amount_atomic", sa.String(32), nullable=False),
        sa.Column("controller_commitment_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("withdrawal_receipt", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_atomic ~ '^[0-9]+$'", name="ck_tokoin_claimable_amount"),
        sa.CheckConstraint(
            "state IN ('CLAIMABLE','WITHDRAWN','RETURNED')",
            name="ck_tokoin_claimable_state",
        ),
        sa.UniqueConstraint(
            "settlement_plan_id", "agent_id", "role", name="uq_tokoin_claimable_agent_role"
        ),
    )
    op.create_index(
        "ix_tokoin_claimable_agent_state", "tokoin_claimable_allocations", ["agent_id", "state"]
    )

    op.create_table(
        "tokoin_knowledge_root_anchors",
        sa.Column("anchor_id", sa.String(30), primary_key=True),
        sa.Column(
            "merkle_batch_id",
            sa.String(30),
            sa.ForeignKey("magna_merkle_batches.batch_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("world_instance_id", sa.String(64), nullable=False),
        sa.Column("merkle_root", sa.String(64), nullable=False),
        sa.Column("previous_root_hash", sa.String(64), nullable=True),
        sa.Column("chain_id", sa.Integer, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("tx_hash", sa.String(66), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("chain_id IN (31337, 84532)", name="ck_tokoin_knowledge_root_chain"),
        sa.CheckConstraint(
            "state IN ('LOCAL_ANCHORED','ONCHAIN_PENDING','ANCHORED','CONFLICT')",
            name="ck_tokoin_knowledge_root_state",
        ),
        sa.UniqueConstraint(
            "world_instance_id", "merkle_root", name="uq_tokoin_knowledge_root"
        ),
    )
    op.create_index(
        "ix_tokoin_knowledge_roots_world",
        "tokoin_knowledge_root_anchors",
        ["world_instance_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tokoin_knowledge_roots_world", table_name="tokoin_knowledge_root_anchors")
    op.drop_table("tokoin_knowledge_root_anchors")
    op.drop_index("ix_tokoin_claimable_agent_state", table_name="tokoin_claimable_allocations")
    op.drop_table("tokoin_claimable_allocations")
    op.drop_index("ix_tokoin_settlement_plans_state", table_name="tokoin_settlement_plans")
    op.drop_table("tokoin_settlement_plans")
    op.drop_index("ix_tokoin_reservations_state", table_name="tokoin_reservations")
    op.drop_table("tokoin_reservations")
    op.drop_index("ix_tokoin_wallet_bindings_state", table_name="tokoin_wallet_bindings")
    op.drop_table("tokoin_wallet_bindings")
    op.drop_index("ix_tokoin_deployments_status", table_name="tokoin_deployment_manifests")
    op.drop_table("tokoin_deployment_manifests")
    op.drop_constraint("ck_magna_receipt_state", "magna_resolution_receipts", type_="check")
    op.create_check_constraint(
        "ck_magna_receipt_state",
        "magna_resolution_receipts",
        "requested_state IN ('PROPOSED','UNDER_TEST','SUPPORTED_ONCE','REPLICATED',"
        "'CONTESTED','REFUTED','INCONCLUSIVE','SUPERSEDED')",
    )
    op.drop_constraint("ck_magna_object_state", "magna_knowledge_objects", type_="check")
    op.create_check_constraint(
        "ck_magna_object_state",
        "magna_knowledge_objects",
        "state IN ('PROPOSED','UNDER_TEST','SUPPORTED_ONCE','REPLICATED',"
        "'CONTESTED','REFUTED','INCONCLUSIVE','SUPERSEDED')",
    )
