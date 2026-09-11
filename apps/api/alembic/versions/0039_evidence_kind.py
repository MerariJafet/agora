"""Typed evidence origin: evidence_kind + certificate_hash (pilot upgrade).

The world must distinguish 'Z3 said unsat' from 'the LLM asserted it'.
"""

import sqlalchemy as sa
from alembic import op

revision = "0039_evidence_kind"
down_revision = "0038_python_test_reviewer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("evidence_kind", sa.String(24), nullable=True))
    op.add_column("evidence", sa.Column("certificate_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence", "certificate_hash")
    op.drop_column("evidence", "evidence_kind")
