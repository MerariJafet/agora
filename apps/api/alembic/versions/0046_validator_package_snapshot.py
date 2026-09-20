"""Freeze each validator's research package on first authenticated retrieval."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0046_validator_package_snapshot"
down_revision = "0045_merge_validator_owner_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("validator_assignments", sa.Column(
        "review_package", postgresql.JSONB(), nullable=True,
    ))
    op.execute("""
        CREATE FUNCTION protect_validator_review_package() RETURNS trigger AS $$
        BEGIN
            IF OLD.review_package IS NOT NULL
               AND NEW.review_package IS DISTINCT FROM OLD.review_package THEN
                RAISE EXCEPTION 'validator review package is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER validator_review_package_immutable
        BEFORE UPDATE ON validator_assignments FOR EACH ROW
        EXECUTE FUNCTION protect_validator_review_package();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER validator_review_package_immutable ON validator_assignments")
    op.execute("DROP FUNCTION protect_validator_review_package()")
    op.drop_column("validator_assignments", "review_package")
