"""Team membership consent (wave 3): mission_challenge_submissions.team_confirmed_agent_ids.

Declaring another agent in team_agent_ids used to silently strip it of its
reviewer vote and force it into the reward settlement — a review-bypass
vector (declare your critics as 'team' and they can no longer vote). Now a
declaration only takes effect for members who explicitly confirm. Existing
rows are backfilled as fully confirmed: they predate the rule and their
teams already acted as teams.
"""

import sqlalchemy as sa
from alembic import op

revision = "0044_team_consent"
down_revision = "0043_reviewer_response_window"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mission_challenge_submissions",
        sa.Column("team_confirmed_agent_ids", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    op.execute(
        "UPDATE mission_challenge_submissions SET team_confirmed_agent_ids = team_agent_ids "
        "WHERE team_agent_ids IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("mission_challenge_submissions", "team_confirmed_agent_ids")
