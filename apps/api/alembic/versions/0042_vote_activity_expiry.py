"""Vote activity confirmation (ADR-0074): mission_challenge_votes.{confirmed_active_at,expired_at}.

Adds two nullable timestamps. confirmed_active_at: set once, permanently, the
first time the voting agent is observed active (any authenticated request)
between casting the vote and its 3-day deadline. expired_at: set once when the
deadline passes without confirmation — from then on the vote is treated as an
abstention by _maybe_resolve and shown as expired in views. An agent that
votes and never reconnects can no longer block a challenge forever; re-casting
the vote clears both fields and starts a fresh window.
"""

import sqlalchemy as sa
from alembic import op

revision = "0042_vote_activity_expiry"
down_revision = "0041_mentions_network"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mission_challenge_votes",
        sa.Column("confirmed_active_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "mission_challenge_votes",
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mission_challenge_votes", "expired_at")
    op.drop_column("mission_challenge_votes", "confirmed_active_at")
