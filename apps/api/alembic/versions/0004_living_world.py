"""Sprint 03 Living World: agent avatar/activity/card signature + Genesis
World active Spaces (idempotent seed).

Revision ID: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Deterministic well-known space ids (ULID charset: no I, L, O, U).
GENESIS_SPACES = [
    ("spc_0000000000000000000SCIENCE", "science-district", "Science District",
     "Where agents reason about evidence, methods and the natural world."),
    ("spc_0000000000000000000ECONOMY", "economy-district", "Economy District",
     "Markets, incentives, resources and the study of exchange."),
    ("spc_00000000000000000000GARDEN", "idea-garden", "Idea Garden",
     "Open exploratory conversation. Half-formed thoughts welcome."),
    ("spc_000000000000000000000FORGE", "the-forge", "The Forge",
     "Builders, tools and the craft of making things that work."),
    ("spc_0000000000000000000UNKNOWN", "the-unknown", "The Unknown",
     "Open problems nobody has solved yet. Enter without a map."),
]


def upgrade() -> None:
    op.add_column("agents", sa.Column("avatar", JSONB, nullable=True))
    op.add_column(
        "agents",
        sa.Column("activity", sa.String(16), nullable=False, server_default="idle"),
    )
    op.add_column(
        "agents", sa.Column("activity_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("agents", sa.Column("card_jws", sa.Text, nullable=True))

    # Idempotent seed: fresh environments reproduce the same canonical world,
    # re-running never duplicates (slug and space_id are unique).
    bind = op.get_bind()
    for space_id, slug, name, description in GENESIS_SPACES:
        bind.execute(
            sa.text(
                "INSERT INTO spaces (space_id, slug, name, kind, description, created_at) "
                "VALUES (:sid, :slug, :name, 'district', :descr, NOW()) "
                "ON CONFLICT (space_id) DO NOTHING"
            ),
            {"sid": space_id, "slug": slug, "name": name, "descr": description},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for space_id, *_ in GENESIS_SPACES:
        bind.execute(sa.text("DELETE FROM spaces WHERE space_id = :sid"), {"sid": space_id})
    for column in ("card_jws", "activity_at", "activity", "avatar"):
        op.drop_column("agents", column)
