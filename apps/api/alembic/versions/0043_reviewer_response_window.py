"""Silent-reviewer response window (ADR-0075): submissions.submitted_at.

Records when a challenge submission entered peer review. It anchors the
reviewer response window: a challenge participant who has cast no vote at
all within the window (counted from the later of the submission entering
review and the participant joining) stops counting toward the unanimity
requirement, exactly like an abstention. Existing non-draft rows are
backfilled with created_at (their drafts were finalized immediately in
practice).
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_reviewer_response_window"
down_revision = "0042_vote_activity_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mission_challenge_submissions",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE mission_challenge_submissions SET submitted_at = created_at "
        "WHERE state != 'draft'"
    )


def downgrade() -> None:
    op.drop_column("mission_challenge_submissions", "submitted_at")
