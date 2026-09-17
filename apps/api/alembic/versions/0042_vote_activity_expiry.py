"""Vote activity confirmation (ADR-0074): mission_challenge_votes.confirmed_active_at.

Adds a single nullable timestamp: set once, permanently, the first time the
voting agent is observed active (a device ping) between casting the vote and
its 3-day deadline. A blocking vote (not resolved, not abstained) whose
deadline has passed without confirmation is treated as an abstention by
_maybe_resolve — an agent that votes and never reconnects can no longer
block a challenge forever.
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


def downgrade() -> None:
    op.drop_column("mission_challenge_votes", "confirmed_active_at")
