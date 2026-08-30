"""TOKOIN blockchain block sealing layer.

Revision ID: 0029_tokoin_blockchain
Revises: 0028_challenge_reward_split
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_tokoin_blockchain"
down_revision = "0028_challenge_reward_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tokoin_blocks",
        sa.Column("block_id", sa.String(30), primary_key=True),
        sa.Column("height", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("first_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("transaction_merkle_root", sa.String(64), nullable=False),
        sa.Column("previous_block_hash", sa.String(64), nullable=True),
        sa.Column("block_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("proof_bundle_hash", sa.String(64), nullable=False),
        sa.Column("proof_bundle", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("height >= 1", name="ck_tokoin_block_height_positive"),
        sa.CheckConstraint("entry_count >= 1", name="ck_tokoin_block_entry_count_positive"),
        sa.CheckConstraint(
            "last_sequence >= first_sequence",
            name="ck_tokoin_block_valid_sequence_range",
        ),
        sa.CheckConstraint(
            "entry_count = last_sequence - first_sequence + 1",
            name="ck_tokoin_block_contiguous_count",
        ),
    )
    op.create_index(
        "ix_tokoin_blocks_range", "tokoin_blocks", ["first_sequence", "last_sequence"]
    )
    op.create_index("ix_tokoin_blocks_created", "tokoin_blocks", ["created_at"])
    op.execute(
        """
        CREATE OR REPLACE FUNCTION agora_tokoin_blocks_immutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'tokoin blocks are append-only (% blocked)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_tokoin_blocks_no_update
            BEFORE UPDATE ON tokoin_blocks
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_blocks_immutable();

        CREATE TRIGGER trg_tokoin_blocks_no_delete
            BEFORE DELETE ON tokoin_blocks
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_blocks_immutable();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tokoin_blocks_no_update ON tokoin_blocks")
    op.execute("DROP TRIGGER IF EXISTS trg_tokoin_blocks_no_delete ON tokoin_blocks")
    op.execute("DROP FUNCTION IF EXISTS agora_tokoin_blocks_immutable")
    op.drop_index("ix_tokoin_blocks_created", table_name="tokoin_blocks")
    op.drop_index("ix_tokoin_blocks_range", table_name="tokoin_blocks")
    op.drop_table("tokoin_blocks")
