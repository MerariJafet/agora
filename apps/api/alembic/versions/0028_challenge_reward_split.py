"""Challenge methodology and reward team split.

Revision ID: 0028_challenge_reward_split
Revises: 0027_forum_consensus
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_challenge_reward_split"
down_revision = "0027_forum_consensus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mission_challenge_submissions",
        sa.Column("team_agent_ids", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mission_challenge_submissions", "team_agent_ids")
