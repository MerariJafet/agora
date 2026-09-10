"""Durable A2A request identity and terminal result receipts.

Revision ID: 0037_a2a_delivery_contract
Revises: 0036_research_information

Additive: legacy tasks keep NULL identities rather than inventing idempotency
for historical duplicate messageIds. Existing terminal artifacts remain readable.
"""

import sqlalchemy as sa
from alembic import op

revision = "0037_a2a_delivery_contract"
down_revision = "0036_research_information"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("a2a_tasks", sa.Column("message_id", sa.String(256), nullable=True))
    op.add_column("a2a_tasks", sa.Column("request_hash", sa.String(64), nullable=True))
    op.add_column("a2a_tasks", sa.Column("result_hash", sa.String(64), nullable=True))
    op.add_column("a2a_tasks", sa.Column("result_reason", sa.String(500), nullable=True))
    op.add_column("a2a_tasks", sa.Column("executor_id", sa.String(36), nullable=True))
    op.create_unique_constraint(
        "uq_a2a_request_identity", "a2a_tasks",
        ["initiator_agent_id", "target_agent_id", "message_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_a2a_request_identity", "a2a_tasks", type_="unique")
    for column in ("executor_id", "result_reason", "result_hash", "request_hash", "message_id"):
        op.drop_column("a2a_tasks", column)
