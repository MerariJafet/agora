"""Explicit computational TEST reviewer provider; no human institution changes."""

import sqlalchemy as sa
from alembic import op

revision = "0038_python_test_reviewer"
down_revision = "0037_a2a_delivery_contract"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_pilot_validator_brain_provider", "institutional_validators", type_="check"
    )
    op.alter_column("institutional_validators", "brain_provider", type_=sa.String(32))
    op.create_check_constraint(
        "ck_pilot_validator_brain_provider",
        "institutional_validators",
        "brain_provider IN ('codex','claude','python-scripted-test')",
    )


def downgrade():
    # PostgreSQL refuses this if scripted rows remain. Never relabel them as LLMs.
    op.drop_constraint(
        "ck_pilot_validator_brain_provider", "institutional_validators", type_="check"
    )
    op.create_check_constraint(
        "ck_pilot_validator_brain_provider",
        "institutional_validators",
        "brain_provider IN ('codex','claude')",
    )
    op.alter_column("institutional_validators", "brain_provider", type_=sa.String(16))
