"""Internal TOKOIN economy: fixed supply, wallets and hash-chained ledger.

Revision ID: 0013
Revises: 0012
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

TOKOIN_SUPPLY = 1_000_000
TREASURY_WALLET_ID = "wal_0000000000000000000TREASRY"
GENESIS_ENTRY_ID = "tko_0000000000000000000G3N3S1S"
GENESIS_HASH = "7f627924cdf125d765aafaedd8637dadcebc8ab18146fa8a492e5dbfcde63114"


def upgrade() -> None:
    op.create_table(
        "tokoin_wallets",
        sa.Column("wallet_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=True),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("balance", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", name="uq_tokoin_wallet_agent"),
        sa.CheckConstraint("balance >= 0", name="ck_tokoin_wallet_nonnegative"),
    )
    op.create_index("ix_tokoin_wallets_agent", "tokoin_wallets", ["agent_id"])

    op.create_table(
        "tokoin_supply",
        sa.Column("currency_code", sa.String(12), primary_key=True),
        sa.Column("max_supply", sa.BigInteger, nullable=False),
        sa.Column("treasury_wallet_id", sa.String(30), nullable=False, unique=True),
        sa.Column("genesis_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_supply = 1000000", name="ck_tokoin_fixed_supply"),
    )

    op.create_table(
        "tokoin_ledger_entries",
        sa.Column("entry_id", sa.String(30), primary_key=True),
        sa.Column("sequence", sa.BigInteger, nullable=False, unique=True),
        sa.Column("entry_type", sa.String(24), nullable=False),
        sa.Column(
            "from_wallet_id",
            sa.String(30),
            sa.ForeignKey("tokoin_wallets.wallet_id"),
            nullable=True,
        ),
        sa.Column(
            "to_wallet_id",
            sa.String(30),
            sa.ForeignKey("tokoin_wallets.wallet_id"),
            nullable=True,
        ),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("currency_code", sa.String(12), nullable=False, server_default="TOKOIN"),
        sa.Column("reason", sa.String(128), nullable=False),
        sa.Column("mission_id", sa.String(30), nullable=True),
        sa.Column("event_id", sa.String(30), nullable=True),
        sa.Column("previous_hash", sa.String(64), nullable=True),
        sa.Column("entry_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_tokoin_entry_positive"),
        sa.CheckConstraint(
            "entry_type IN ('genesis','transfer','mission_reward','adjustment_reversal')",
            name="ck_tokoin_entry_type",
        ),
    )
    op.create_index("ix_tokoin_ledger_wallet_from", "tokoin_ledger_entries", ["from_wallet_id"])
    op.create_index("ix_tokoin_ledger_wallet_to", "tokoin_ledger_entries", ["to_wallet_id"])
    op.create_index("ix_tokoin_ledger_mission", "tokoin_ledger_entries", ["mission_id"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION agora_tokoin_ledger_immutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'tokoin ledger is append-only (% blocked)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_tokoin_ledger_no_update
            BEFORE UPDATE ON tokoin_ledger_entries
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_ledger_immutable();

        CREATE TRIGGER trg_tokoin_ledger_no_delete
            BEFORE DELETE ON tokoin_ledger_entries
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_ledger_immutable();
        """
    )

    created_at = datetime(2026, 8, 25, tzinfo=UTC)
    wallets = sa.table(
        "tokoin_wallets",
        sa.column("wallet_id"),
        sa.column("agent_id"),
        sa.column("label"),
        sa.column("balance"),
        sa.column("created_at"),
        sa.column("updated_at"),
    )
    supply = sa.table(
        "tokoin_supply",
        sa.column("currency_code"),
        sa.column("max_supply"),
        sa.column("treasury_wallet_id"),
        sa.column("genesis_hash"),
        sa.column("created_at"),
    )
    ledger = sa.table(
        "tokoin_ledger_entries",
        sa.column("entry_id"),
        sa.column("sequence"),
        sa.column("entry_type"),
        sa.column("from_wallet_id"),
        sa.column("to_wallet_id"),
        sa.column("amount"),
        sa.column("currency_code"),
        sa.column("reason"),
        sa.column("mission_id"),
        sa.column("event_id"),
        sa.column("previous_hash"),
        sa.column("entry_hash"),
        sa.column("created_at"),
    )
    op.bulk_insert(
        wallets,
        [{
            "wallet_id": TREASURY_WALLET_ID,
            "agent_id": None,
            "label": "AGORA World Treasury",
            "balance": TOKOIN_SUPPLY,
            "created_at": created_at,
            "updated_at": created_at,
        }],
    )
    op.bulk_insert(
        supply,
        [{
            "currency_code": "TOKOIN",
            "max_supply": TOKOIN_SUPPLY,
            "treasury_wallet_id": TREASURY_WALLET_ID,
            "genesis_hash": GENESIS_HASH,
            "created_at": created_at,
        }],
    )
    op.bulk_insert(
        ledger,
        [{
            "entry_id": GENESIS_ENTRY_ID,
            "sequence": 1,
            "entry_type": "genesis",
            "from_wallet_id": None,
            "to_wallet_id": TREASURY_WALLET_ID,
            "amount": TOKOIN_SUPPLY,
            "currency_code": "TOKOIN",
            "reason": "world_genesis_supply",
            "mission_id": None,
            "event_id": None,
            "previous_hash": None,
            "entry_hash": GENESIS_HASH,
            "created_at": created_at,
        }],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tokoin_ledger_no_update ON tokoin_ledger_entries")
    op.execute("DROP TRIGGER IF EXISTS trg_tokoin_ledger_no_delete ON tokoin_ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS agora_tokoin_ledger_immutable")
    op.drop_table("tokoin_ledger_entries")
    op.drop_table("tokoin_supply")
    op.drop_index("ix_tokoin_wallets_agent", table_name="tokoin_wallets")
    op.drop_table("tokoin_wallets")
