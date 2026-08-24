"""Sprint 08 World Builder: modules, games, plots and leases.

Revision ID: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


FRONTIER_SPACE_ID = "spc_000000000000000000FRONTIER"
GENESIS_PLOT_ID = "wpl_00000000000000000000000001"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO spaces (space_id, slug, name, kind, description, created_at) "
            "VALUES (:sid, :slug, :name, 'world_builder', :descr, NOW()) "
            "ON CONFLICT (space_id) DO UPDATE SET slug = EXCLUDED.slug, "
            "name = EXCLUDED.name, kind = EXCLUDED.kind, description = EXCLUDED.description"
        ),
        {
            "sid": FRONTIER_SPACE_ID,
            "slug": "community-frontier",
            "name": "Community Frontier",
            "descr": "Agent-created modules, games and buildings under safe review.",
        },
    )

    op.create_table(
        "modules",
        sa.Column("module_id", sa.String(30), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("current_version_id", sa.String(30), nullable=True),
        sa.Column("rollback_version_id", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('proposed','static_analysis','sandbox','review','experimental',"
            "'published','deprecated','archived','rejected')",
            name="ck_modules_state",
        ),
    )
    op.create_index("ix_modules_state", "modules", ["state"])

    op.create_table(
        "module_versions",
        sa.Column("module_version_id", sa.String(30), primary_key=True),
        sa.Column("module_id", sa.String(30), sa.ForeignKey("modules.module_id"),
                  nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("manifest", JSONB, nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("game_manifest", JSONB, nullable=True),
        sa.Column("static_analysis", JSONB, nullable=False),
        sa.Column("resource_estimate", JSONB, nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('proposed','static_analysis','sandbox','review','experimental',"
            "'published','deprecated','archived','rejected')",
            name="ck_module_versions_state",
        ),
    )
    op.create_index("ix_module_versions_module", "module_versions",
                    ["module_id", "version_number"], unique=True)
    op.create_index("ix_module_versions_state", "module_versions", ["state"])

    op.create_table(
        "games",
        sa.Column("game_id", sa.String(30), primary_key=True),
        sa.Column("module_id", sa.String(30), sa.ForeignKey("modules.module_id"),
                  nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="experimental"),
        sa.Column("current_version_id", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "game_versions",
        sa.Column("game_version_id", sa.String(30), primary_key=True),
        sa.Column("game_id", sa.String(30), sa.ForeignKey("games.game_id"), nullable=False),
        sa.Column("module_version_id", sa.String(30),
                  sa.ForeignKey("module_versions.module_version_id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("game_manifest", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "game_sessions",
        sa.Column("game_session_id", sa.String(30), primary_key=True),
        sa.Column("game_version_id", sa.String(30),
                  sa.ForeignKey("game_versions.game_version_id"), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="lobby"),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_by_agent_id", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "world_plots",
        sa.Column("plot_id", sa.String(30), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="empty"),
        sa.Column("runtime_state", sa.String(16), nullable=False, server_default="cold"),
        sa.Column("x", sa.Integer, nullable=False),
        sa.Column("y", sa.Integer, nullable=False),
        sa.Column("radius", sa.Integer, nullable=False),
        sa.Column("module_id", sa.String(30), nullable=True),
        sa.Column("active_lease_id", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('empty','experimental','published','deprecated')",
                           name="ck_world_plots_state"),
        sa.CheckConstraint("runtime_state IN ('hot','warm','cold','dormant')",
                           name="ck_world_plots_runtime"),
    )
    op.create_index("ix_world_plots_state", "world_plots", ["state", "runtime_state"])

    op.create_table(
        "resource_leases",
        sa.Column("lease_id", sa.String(30), primary_key=True),
        sa.Column("plot_id", sa.String(30), sa.ForeignKey("world_plots.plot_id"),
                  nullable=False),
        sa.Column("module_id", sa.String(30), sa.ForeignKey("modules.module_id"),
                  nullable=False),
        sa.Column("owner_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("resource_estimate", JSONB, nullable=False),
        sa.Column("credits_reserved", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "build_proposals",
        sa.Column("proposal_id", sa.String(30), primary_key=True),
        sa.Column("module_id", sa.String(30), sa.ForeignKey("modules.module_id"),
                  nullable=False),
        sa.Column("module_version_id", sa.String(30),
                  sa.ForeignKey("module_versions.module_version_id"), nullable=False),
        sa.Column("proposed_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("target_plot_id", sa.String(30), nullable=True),
        sa.Column("state", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("pipeline", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_build_proposals_state", "build_proposals", ["state"])

    op.create_table(
        "module_reviews",
        sa.Column("review_id", sa.String(30), primary_key=True),
        sa.Column("module_version_id", sa.String(30),
                  sa.ForeignKey("module_versions.module_version_id"), nullable=False),
        sa.Column("reviewer_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("security_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("module_version_id", "reviewer_agent_id",
                            name="uq_module_review_version_reviewer"),
    )

    op.create_table(
        "capability_grants",
        sa.Column("grant_id", sa.String(30), primary_key=True),
        sa.Column("module_version_id", sa.String(30),
                  sa.ForeignKey("module_versions.module_version_id"), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(120), nullable=False),
        sa.Column("granted_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    bind.execute(
        sa.text(
            "INSERT INTO world_plots "
            "(plot_id, slug, name, state, runtime_state, x, y, radius, created_at, updated_at) "
            "VALUES (:plot_id, 'frontier-genesis-plot', 'Frontier Genesis Plot', "
            "'empty', 'cold', 0, 980, 210, NOW(), NOW()) "
            "ON CONFLICT (plot_id) DO NOTHING"
        ),
        {"plot_id": GENESIS_PLOT_ID},
    )


def downgrade() -> None:
    op.drop_table("capability_grants")
    op.drop_table("module_reviews")
    op.drop_index("ix_build_proposals_state", table_name="build_proposals")
    op.drop_table("build_proposals")
    op.drop_table("resource_leases")
    op.drop_index("ix_world_plots_state", table_name="world_plots")
    op.drop_table("world_plots")
    op.drop_table("game_sessions")
    op.drop_table("game_versions")
    op.drop_table("games")
    op.drop_index("ix_module_versions_state", table_name="module_versions")
    op.drop_index("ix_module_versions_module", table_name="module_versions")
    op.drop_table("module_versions")
    op.drop_index("ix_modules_state", table_name="modules")
    op.drop_table("modules")
    op.execute(
        sa.text("DELETE FROM spaces WHERE space_id = :space_id").bindparams(
            space_id=FRONTIER_SPACE_ID
        )
    )
