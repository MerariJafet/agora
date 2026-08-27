"""Formal action plane: challenge draft and withdrawal states.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_mission_challenge_submission_state",
        "mission_challenge_submissions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mission_challenge_submission_state",
        "mission_challenge_submissions",
        "state IN ('draft','submitted','accepted','rejected','withdrawn')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_mission_challenge_submission_state",
        "mission_challenge_submissions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_mission_challenge_submission_state",
        "mission_challenge_submissions",
        "state IN ('submitted','accepted','rejected')",
    )
