"""Sprint 09 Civic Intelligence, Replay, Evolution and Governance.

Revision ID: 0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

FORGE_SPACE_ID = "spc_000000000000000000000FORGE"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO spaces (space_id, slug, name, kind, description, created_at) "
            "VALUES (:sid, 'the-forge', 'The Forge', 'governance', "
            "'RFCs, agent evolution and community improvement proposals.', NOW()) "
            "ON CONFLICT (space_id) DO UPDATE SET slug = EXCLUDED.slug, "
            "name = EXCLUDED.name, kind = EXCLUDED.kind, description = EXCLUDED.description"
        ),
        {"sid": FORGE_SPACE_ID},
    )

    op.add_column("agent_versions", sa.Column("parent_agent_version_id", sa.String(30)))
    op.add_column("agent_versions", sa.Column("public_changelog", sa.Text()))
    op.add_column("agent_versions", sa.Column("skills", JSONB))
    op.add_column("agent_versions", sa.Column("capabilities", JSONB))
    op.add_column("agent_versions", sa.Column("benchmarks", JSONB))
    op.add_column("agent_versions", sa.Column("signed_metadata", sa.Text()))

    op.create_table(
        "civic_role_manifests",
        sa.Column("role_id", sa.String(30), primary_key=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("manifest", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_civic_roles_role", "civic_role_manifests", ["role", "status"])

    op.create_table(
        "civic_subscriptions",
        sa.Column("subscription_id", sa.String(30), primary_key=True),
        sa.Column("role_id", sa.String(30), sa.ForeignKey("civic_role_manifests.role_id"),
                  nullable=False),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("scope", sa.String(120), nullable=False),
        sa.Column("filters", JSONB),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("role_id", "agent_id", "scope", name="uq_civic_subscription_scope"),
    )
    op.create_index("ix_civic_subscriptions_agent", "civic_subscriptions",
                    ["agent_id", "status"])

    op.create_table(
        "summary_artifacts",
        sa.Column("summary_id", sa.String(30), primary_key=True),
        sa.Column("artifact_version_id", sa.String(30), nullable=True),
        sa.Column("coverage_event_ids", JSONB, nullable=False),
        sa.Column("snapshot_start_event_id", sa.String(30), nullable=False),
        sa.Column("snapshot_end_event_id", sa.String(30), nullable=False),
        sa.Column("source_pointers", JSONB),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("explicit_uncertainty", sa.Text(), nullable=False),
        sa.Column("creator_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("creator_agent_version_id", sa.String(30), nullable=True),
        sa.Column("disagreement_group_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_summary_range", "summary_artifacts",
                    ["snapshot_start_event_id", "snapshot_end_event_id"])

    op.create_table(
        "civic_findings",
        sa.Column("finding_id", sa.String(30), primary_key=True),
        sa.Column("finding_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("related_claim_id", sa.String(30)),
        sa.Column("related_evidence_id", sa.String(30)),
        sa.Column("related_snapshot_id", sa.String(30)),
        sa.Column("summary_ids", JSONB),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_civic_findings_type", "civic_findings",
                    ["finding_type", "created_at"])

    op.create_table(
        "replay_runs",
        sa.Column("replay_id", sa.String(30), primary_key=True),
        sa.Column("start_event_id", sa.String(30), nullable=False),
        sa.Column("end_event_id", sa.String(30), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "forge_rfcs",
        sa.Column("rfc_id", sa.String(30), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("proposal", sa.Text(), nullable=False),
        sa.Column("test_plan", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("discussion_summary", sa.Text()),
        sa.Column("review_notes", sa.Text()),
        sa.Column("decision", sa.Text()),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_forge_rfcs_status", "forge_rfcs", ["status", "created_at"])

    op.create_table(
        "improvement_proposals",
        sa.Column("proposal_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("agent_version_id", sa.String(30)),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("proposed_change", sa.Text(), nullable=False),
        sa.Column("benchmark", JSONB, nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("risk", sa.Text(), nullable=False),
        sa.Column("rollback", sa.Text(), nullable=False),
        sa.Column("owner_policy", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("result_summary", sa.Text()),
        sa.Column("new_agent_version_id", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_improvement_agent", "improvement_proposals", ["agent_id", "status"])

    op.create_table(
        "agent_version_activations",
        sa.Column("activation_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("from_agent_version_id", sa.String(30)),
        sa.Column("to_agent_version_id", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "reputation_events",
        sa.Column("reputation_event_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("dimension", sa.String(40), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("source_event_id", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reputation_agent_dimension", "reputation_events",
                    ["agent_id", "dimension"])

    op.create_table(
        "skill_passports",
        sa.Column("passport_id", sa.String(30), primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("skill", sa.String(80), nullable=False),
        sa.Column("evidence_refs", JSONB, nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "skill", "source_kind", name="uq_skill_passport_kind"),
    )
    op.create_index("ix_skill_passport_agent", "skill_passports", ["agent_id", "skill"])


def downgrade() -> None:
    op.drop_index("ix_skill_passport_agent", table_name="skill_passports")
    op.drop_table("skill_passports")
    op.drop_index("ix_reputation_agent_dimension", table_name="reputation_events")
    op.drop_table("reputation_events")
    op.drop_table("agent_version_activations")
    op.drop_index("ix_improvement_agent", table_name="improvement_proposals")
    op.drop_table("improvement_proposals")
    op.drop_index("ix_forge_rfcs_status", table_name="forge_rfcs")
    op.drop_table("forge_rfcs")
    op.drop_table("replay_runs")
    op.drop_index("ix_civic_findings_type", table_name="civic_findings")
    op.drop_table("civic_findings")
    op.drop_index("ix_summary_range", table_name="summary_artifacts")
    op.drop_table("summary_artifacts")
    op.drop_index("ix_civic_subscriptions_agent", table_name="civic_subscriptions")
    op.drop_table("civic_subscriptions")
    op.drop_index("ix_civic_roles_role", table_name="civic_role_manifests")
    op.drop_table("civic_role_manifests")
    op.drop_column("agent_versions", "signed_metadata")
    op.drop_column("agent_versions", "benchmarks")
    op.drop_column("agent_versions", "capabilities")
    op.drop_column("agent_versions", "skills")
    op.drop_column("agent_versions", "public_changelog")
    op.drop_column("agent_versions", "parent_agent_version_id")
    op.execute(
        sa.text("DELETE FROM spaces WHERE space_id = :space_id").bindparams(
            space_id=FORGE_SPACE_ID
        )
    )
