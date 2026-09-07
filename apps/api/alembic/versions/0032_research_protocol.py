"""Research genealogy, institutional validation and reward locks.

Revision ID: 0032_research_protocol
Revises: 0031_tokoin_control_plane_owner
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_research_protocol"
down_revision = "0031_tokoin_control_plane_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_magna_object_type", "magna_knowledge_objects", type_="check")
    op.create_check_constraint(
        "ck_magna_object_type",
        "magna_knowledge_objects",
        "object_type IN ("
        "'research_question','hypothesis','claim','method','registered_protocol',"
        "'protocol_amendment','dataset','artifact_version','experiment_run','evidence',"
        "'contribution','replication_plan','replication','review','dissent','outcome',"
        "'reproducibility_capsule','validation_package','challenge','question',"
        "'experiment_proposal','experiment_result','observation','proof','counterexample',"
        "'critique','refutation','correction','simulation','literature_reference','synthesis',"
        "'candidate_solution','final_solution','institutional_review','publication_artifact'"
        ")",
    )
    op.create_table(
        "research_candidate_snapshots",
        sa.Column("candidate_id", sa.String(30), primary_key=True),
        sa.Column(
            "challenge_id", sa.String(30), sa.ForeignKey("missions.mission_id"), nullable=False
        ),
        sa.Column(
            "submission_id",
            sa.String(30),
            sa.ForeignKey("mission_challenge_submissions.submission_id"),
            nullable=False,
        ),
        sa.Column("candidate_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column(
            "final_solution_object_id",
            sa.String(30),
            sa.ForeignKey("magna_knowledge_objects.object_id"),
            nullable=False,
        ),
        sa.Column("manuscript_artifact_version_id", sa.String(30)),
        sa.Column("knowledge_root_hash", sa.String(64), nullable=False),
        sa.Column("consensus_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("protocol_version", sa.String(24), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_by_agent_id",
            sa.String(30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("created_by_agent_version_id", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "challenge_id", "candidate_version", name="uq_research_candidate_version"
        ),
    )
    op.create_index(
        "ix_research_candidate_challenge",
        "research_candidate_snapshots",
        ["challenge_id", "state"],
    )
    op.create_table(
        "research_institutions",
        sa.Column("institution_id", sa.String(30), primary_key=True),
        sa.Column("legal_entity_id", sa.String(160), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("jurisdiction", sa.String(80), nullable=False),
        sa.Column(
            "representative_owner_id",
            sa.String(30),
            sa.ForeignKey("users.user_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("signing_public_key", sa.String(64), nullable=False),
        sa.Column("credential_reference", sa.String(500), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("payout_address", sa.String(128)),
        sa.Column("conflict_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("verified_by_owner_id", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_research_institution_state", "research_institutions", ["state"])
    op.create_table(
        "institutional_reviews",
        sa.Column("review_id", sa.String(30), primary_key=True),
        sa.Column(
            "institution_id",
            sa.String(30),
            sa.ForeignKey("research_institutions.institution_id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(30),
            sa.ForeignKey("research_candidate_snapshots.candidate_id"),
            nullable=False,
        ),
        sa.Column("verdict", sa.String(40), nullable=False),
        sa.Column("methodology_review", sa.Text(), nullable=False),
        sa.Column("evidence_review", sa.Text(), nullable=False),
        sa.Column("paper_review", sa.Text(), nullable=False),
        sa.Column("experiment_review", sa.Text(), nullable=False),
        sa.Column("conflict_declaration", sa.Text(), nullable=False),
        sa.Column("signed_payload_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "institution_id", "candidate_id", name="uq_institution_candidate_review"
        ),
    )
    op.create_index(
        "ix_institutional_reviews_candidate",
        "institutional_reviews",
        ["candidate_id", "verdict"],
    )
    op.create_table(
        "research_contribution_scores",
        sa.Column("score_id", sa.String(30), primary_key=True),
        sa.Column("challenge_id", sa.String(30), nullable=False),
        sa.Column(
            "object_id",
            sa.String(30),
            sa.ForeignKey("magna_knowledge_objects.object_id"),
            nullable=False,
        ),
        sa.Column("author_agent_id", sa.String(30), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(), nullable=False),
        sa.Column("weighted_score", sa.Integer(), nullable=False),
        sa.Column("explanation", postgresql.JSONB(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("object_id", "algorithm_version", name="uq_research_score_object_algo"),
    )
    op.create_index(
        "ix_research_scores_challenge",
        "research_contribution_scores",
        ["challenge_id", "weighted_score"],
    )
    op.create_table(
        "research_reward_calculations",
        sa.Column("reward_id", sa.String(30), primary_key=True),
        sa.Column("challenge_id", sa.String(30), nullable=False),
        sa.Column(
            "candidate_id",
            sa.String(30),
            sa.ForeignKey("research_candidate_snapshots.candidate_id"),
            nullable=False,
        ),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("total_aceros", sa.BigInteger(), nullable=False),
        sa.Column("allocation", postgresql.JSONB(), nullable=False),
        sa.Column("genealogy_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("explanation", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "candidate_id", "algorithm_version", name="uq_research_reward_candidate"
        ),
    )
    op.create_index(
        "ix_research_rewards_challenge",
        "research_reward_calculations",
        ["challenge_id", "state"],
    )
    op.create_table(
        "research_publication_packages",
        sa.Column("package_id", sa.String(30), primary_key=True),
        sa.Column("challenge_id", sa.String(30), nullable=False),
        sa.Column(
            "candidate_id",
            sa.String(30),
            sa.ForeignKey("research_candidate_snapshots.candidate_id"),
            nullable=False,
        ),
        sa.Column("manuscript_artifact_version_id", sa.String(30)),
        sa.Column("responsible_institution_ids", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("package_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("candidate_id", name="uq_research_publication_candidate"),
    )
    op.create_index(
        "ix_research_publications_challenge",
        "research_publication_packages",
        ["challenge_id", "state"],
    )
    op.execute(
        """
        UPDATE missions
        SET resolution_policy = 'institutional_research_v1',
            completion_policy = completion_policy || '{
              "institutional_quorum": 2,
              "consensus_is_not_truth": true,
              "final_reward_blocked_pending_institutional_quorum": true
            }'::jsonb
        WHERE challenge_kind IN ('institutional_research_test', 'research_consensus_test')
          AND state NOT IN ('completed', 'failed', 'cancelled', 'archived')
        """
    )


def downgrade() -> None:
    tables = [
        "research_publication_packages",
        "research_reward_calculations",
        "research_contribution_scores",
        "institutional_reviews",
        "research_institutions",
        "research_candidate_snapshots",
    ]
    for table in tables:
        op.drop_table(table)
    op.drop_constraint("ck_magna_object_type", "magna_knowledge_objects", type_="check")
    op.create_check_constraint(
        "ck_magna_object_type",
        "magna_knowledge_objects",
        "object_type IN ("
        "'research_question','hypothesis','claim','method','registered_protocol',"
        "'protocol_amendment','dataset','artifact_version','experiment_run','evidence',"
        "'contribution','replication_plan','replication','review','dissent','outcome',"
        "'reproducibility_capsule','validation_package'"
        ")",
    )
