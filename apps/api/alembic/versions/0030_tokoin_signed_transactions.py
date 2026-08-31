"""TOKOIN signed transaction authorizations.

Revision ID: 0030_tokoin_signed_transactions
Revises: 0029_tokoin_blockchain
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_tokoin_signed_transactions"
down_revision = "0029_tokoin_blockchain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tokoin_transaction_authorizations",
        sa.Column("authorization_id", sa.String(30), primary_key=True),
        sa.Column(
            "entry_id",
            sa.String(30),
            sa.ForeignKey("tokoin_ledger_entries.entry_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("authorization_type", sa.String(32), nullable=False),
        sa.Column(
            "signer_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=True
        ),
        sa.Column(
            "signer_device_id", sa.String(30), sa.ForeignKey("devices.device_id"), nullable=True
        ),
        sa.Column("signer_public_key", sa.String(64), nullable=True),
        sa.Column("nonce", sa.String(64), nullable=True),
        sa.Column("message_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("signer_device_id", "nonce", name="uq_tokoin_auth_device_nonce"),
        sa.CheckConstraint(
            "authorization_type IN ('agent_wallet_signature','treasury_policy','genesis')",
            name="ck_tokoin_authorization_type",
        ),
        sa.CheckConstraint(
            """
            (
                authorization_type = 'agent_wallet_signature'
                AND signer_agent_id IS NOT NULL
                AND signer_device_id IS NOT NULL
                AND signer_public_key IS NOT NULL
                AND nonce IS NOT NULL
                AND signature IS NOT NULL
            )
            OR authorization_type IN ('treasury_policy','genesis')
            """,
            name="ck_tokoin_signed_auth_complete",
        ),
    )
    op.create_index(
        "ix_tokoin_auth_entry", "tokoin_transaction_authorizations", ["entry_id"]
    )
    op.create_index(
        "ix_tokoin_auth_signer_agent",
        "tokoin_transaction_authorizations",
        ["signer_agent_id"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION agora_tokoin_transaction_authorizations_immutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'tokoin transaction authorizations are append-only (% blocked)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_tokoin_auth_no_update
            BEFORE UPDATE ON tokoin_transaction_authorizations
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_transaction_authorizations_immutable();

        CREATE TRIGGER trg_tokoin_auth_no_delete
            BEFORE DELETE ON tokoin_transaction_authorizations
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_transaction_authorizations_immutable();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_tokoin_auth_no_update ON tokoin_transaction_authorizations"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_tokoin_auth_no_delete ON tokoin_transaction_authorizations"
    )
    op.execute("DROP FUNCTION IF EXISTS agora_tokoin_transaction_authorizations_immutable")
    op.drop_index("ix_tokoin_auth_signer_agent", table_name="tokoin_transaction_authorizations")
    op.drop_index("ix_tokoin_auth_entry", table_name="tokoin_transaction_authorizations")
    op.drop_table("tokoin_transaction_authorizations")
