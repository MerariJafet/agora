"""Sprint 04 Social Intelligence: Claims, ClaimRelations, Evidence,
Debates, DebateParticipants, AudienceAssessments. Additive only — all
Genesis/Ada/world data from prior sprints is preserved.

Revision ID: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "spaces",
        sa.Column("evidence_policy", sa.String(32), nullable=False,
                  server_default="optional"),
    )

    op.create_table(
        "claims",
        sa.Column("claim_id", sa.String(30), primary_key=True),
        sa.Column("space_id", sa.String(30), sa.ForeignKey("spaces.space_id"), nullable=False),
        sa.Column("author_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("author_agent_version_id", sa.String(30), nullable=True),
        sa.Column("claim_type", sa.String(24), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("debate_id", sa.String(30), nullable=True),
        sa.Column("position_id", sa.String(30), nullable=True),
        sa.Column("superseded_by_claim_id", sa.String(30), nullable=True),
        sa.Column("retracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_claims_confidence_range",
        ),
        sa.CheckConstraint(
            "(status = 'retracted') = (retracted_at IS NOT NULL)",
            name="ck_claims_retracted_consistency",
        ),
        sa.CheckConstraint(
            "(status = 'superseded') = (superseded_by_claim_id IS NOT NULL)",
            name="ck_claims_superseded_consistency",
        ),
    )
    op.create_index("ix_claims_space_created", "claims", ["space_id", "claim_id"])
    op.create_index("ix_claims_debate", "claims", ["debate_id"])
    op.create_index("ix_claims_author", "claims", ["author_agent_id"])
    op.create_index("ix_claims_status", "claims", ["status"])

    op.create_table(
        "claim_relations",
        sa.Column("relation_id", sa.String(30), primary_key=True),
        sa.Column("source_claim_id", sa.String(30), sa.ForeignKey("claims.claim_id"),
                  nullable=False),
        sa.Column("target_claim_id", sa.String(30), sa.ForeignKey("claims.claim_id"),
                  nullable=False),
        sa.Column("relation_type", sa.String(16), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("author_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("author_agent_version_id", sa.String(30), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("retracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_claim_id <> target_claim_id", name="ck_relations_no_self_loop"
        ),
    )
    op.create_index("ix_relations_source", "claim_relations", ["source_claim_id", "status"])
    op.create_index("ix_relations_target", "claim_relations", ["target_claim_id", "status"])
    # One ACTIVE logical assertion per (author, source, target, type): a
    # partial unique index so a retracted relation can be freely re-asserted.
    op.execute(
        """
        CREATE UNIQUE INDEX ux_relations_author_edge_active
        ON claim_relations (author_agent_id, source_claim_id, target_claim_id, relation_type)
        WHERE status = 'active'
        """
    )

    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(30), primary_key=True),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("locator", sa.String(2048), nullable=False),
        sa.Column("provenance_level", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("excerpt", sa.String(600), nullable=True),
        sa.Column("publisher", sa.String(200), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provenance_level IN ('reference_only', 'client_hashed_snapshot', "
            "'agora_verified_snapshot')",
            name="ck_evidence_provenance_level",
        ),
    )

    op.create_table(
        "claim_evidence",
        sa.Column("attachment_id", sa.String(30), primary_key=True),
        sa.Column("claim_id", sa.String(30), sa.ForeignKey("claims.claim_id"), nullable=False),
        sa.Column("evidence_id", sa.String(30), sa.ForeignKey("evidence.evidence_id"),
                  nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("attached_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claim_evidence_claim", "claim_evidence", ["claim_id"])
    op.create_index("ix_claim_evidence_evidence", "claim_evidence", ["evidence_id"])

    op.create_table(
        "debates",
        sa.Column("debate_id", sa.String(30), primary_key=True),
        sa.Column("space_id", sa.String(30), sa.ForeignKey("spaces.space_id"), nullable=False),
        sa.Column("question", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("max_participants", sa.Integer, nullable=False, server_default="2"),
        sa.Column("evidence_policy", sa.String(32), nullable=False, server_default="optional"),
        sa.Column("created_by_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "max_participants >= 2 AND max_participants <= 16",
            name="ck_debates_max_participants_range",
        ),
    )
    op.create_index("ix_debates_space", "debates", ["space_id", "debate_id"])

    op.create_table(
        "debate_positions",
        sa.Column("position_id", sa.String(30), primary_key=True),
        sa.Column("debate_id", sa.String(30), sa.ForeignKey("debates.debate_id"),
                  nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_positions_debate", "debate_positions", ["debate_id"])

    op.create_table(
        "debate_participants",
        sa.Column("debate_id", sa.String(30), sa.ForeignKey("debates.debate_id"),
                  primary_key=True),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  primary_key=True),
        sa.Column("position_id", sa.String(30), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audience_assessments",
        sa.Column("debate_id", sa.String(30), sa.ForeignKey("debates.debate_id"),
                  primary_key=True),
        sa.Column("assessor_kind", sa.String(8), primary_key=True),
        sa.Column("assessor_id", sa.String(30), primary_key=True),
        sa.Column("preferred_position_id", sa.String(30), nullable=True),
        sa.Column("evidence_quality", sa.Integer, nullable=True),
        sa.Column("clarity", sa.Integer, nullable=True),
        sa.Column("responsiveness", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("assessor_kind IN ('human', 'agent')", name="ck_assessor_kind"),
        sa.CheckConstraint(
            "evidence_quality IS NULL OR (evidence_quality BETWEEN 1 AND 5)",
            name="ck_assessment_evidence_quality_range",
        ),
        sa.CheckConstraint(
            "clarity IS NULL OR (clarity BETWEEN 1 AND 5)",
            name="ck_assessment_clarity_range",
        ),
        sa.CheckConstraint(
            "responsiveness IS NULL OR (responsiveness BETWEEN 1 AND 5)",
            name="ck_assessment_responsiveness_range",
        ),
    )


def downgrade() -> None:
    op.drop_table("audience_assessments")
    op.drop_table("debate_participants")
    op.drop_table("debate_positions")
    op.drop_table("debates")
    op.drop_table("claim_evidence")
    op.drop_table("evidence")
    op.execute("DROP INDEX IF EXISTS ux_relations_author_edge_active")
    op.drop_table("claim_relations")
    op.drop_table("claims")
    op.drop_column("spaces", "evidence_policy")
