"""Add runtime metadata to signed rule delivery states.

Revision ID: 0018
Revises: 0017_world_hygiene_rule_delivery
Create Date: 2026-08-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rule_delivery_states",
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rule_delivery_states",
        sa.Column("cursor_advanced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rule_delivery_states",
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rule_delivery_states",
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rule_delivery_states",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rule_delivery_states",
        sa.Column("runtime_version", sa.String(64), nullable=True),
    )
    op.add_column(
        "rule_delivery_states",
        sa.Column("runtime_protocol_version", sa.String(64), nullable=True),
    )
    op.add_column(
        "rule_delivery_states",
        sa.Column("verification_result", sa.String(64), nullable=True),
    )
    op.add_column(
        "rule_delivery_states",
        sa.Column("attestation_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rule_delivery_states", "attestation_metadata")
    op.drop_column("rule_delivery_states", "verification_result")
    op.drop_column("rule_delivery_states", "runtime_protocol_version")
    op.drop_column("rule_delivery_states", "runtime_version")
    op.drop_column("rule_delivery_states", "next_retry_at")
    op.drop_column("rule_delivery_states", "last_success_at")
    op.drop_column("rule_delivery_states", "last_poll_at")
    op.drop_column("rule_delivery_states", "cursor_advanced_at")
    op.drop_column("rule_delivery_states", "fetched_at")
