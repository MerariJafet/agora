"""Synthetic institutional validators and blind dual review.

Revision ID: 0034_institutional_validators
Revises: 0033_research_idempotency
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_institutional_validators"
down_revision = "0033_research_idempotency"
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
        "'candidate_solution','final_solution','institutional_review','publication_artifact',"
        "'review_finding','reproduction_attempt','reproduction_result','validator_objection',"
        "'validator_requested_revision','validator_approval'"
        ")",
    )
    op.drop_constraint("ck_magna_edge_relation", "magna_knowledge_edges", type_="check")
    op.create_check_constraint(
        "ck_magna_edge_relation",
        "magna_knowledge_edges",
        "relation_type IN ("
        "'was_derived_from','used','was_generated_by','was_attributed_to','supports',"
        "'refutes','does_not_resolve','replicates','reviews','dissents_from','supersedes',"
        "'depends_on','contradicts','uses','parent_of','reproduces','fails_to_reproduce',"
        "'requests_revision_of','approves_version'"
        ")",
    )
    op.create_table(
        "institutional_validators",
        sa.Column("validator_id", sa.String(30), primary_key=True),
        sa.Column("actor_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("validator_type", sa.String(40), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("institution_name", sa.String(200), nullable=False),
        sa.Column("institution_type", sa.String(64), nullable=False),
        sa.Column("legal_entity_id", sa.String(160), nullable=False, unique=True),
        sa.Column("domain", sa.String(253), nullable=False, unique=True),
        sa.Column("jurisdiction", sa.String(80), nullable=False),
        sa.Column("institution_mode", sa.String(32), nullable=False),
        sa.Column("accreditation_status", sa.String(32), nullable=False),
        sa.Column("public_label", sa.String(200), nullable=False),
        sa.Column("brain_provider", sa.String(16), nullable=False),
        sa.Column("review_role", sa.String(48), nullable=False),
        sa.Column("synthetic_or_human", sa.String(16), nullable=False),
        sa.Column("world_instance_id", sa.String(64), nullable=False),
        sa.Column("public_key", sa.String(64), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("scientific_domains", postgresql.JSONB(), nullable=False),
        sa.Column("review_history", postgresql.JSONB(), nullable=False),
        sa.Column("reputation_score", sa.Integer(), nullable=False),
        sa.Column("active_status", sa.Boolean(), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("representative_owner_id", sa.String(30), sa.ForeignKey("users.user_id")),
        sa.Column("verified_by_owner_id", sa.String(30), sa.ForeignKey("users.user_id")),
        sa.Column("verification_evidence_hash", sa.String(64)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("actor_id", name="uq_institutional_validator_actor"),
        sa.CheckConstraint(
            "validator_type = 'INSTITUTIONAL_VALIDATOR_TEST' "
            "AND synthetic_or_human = 'synthetic' "
            "AND institution_mode = 'simulated_test' "
            "AND jurisdiction = 'TEST' "
            "AND accreditation_status = 'NOT_REAL'",
            name="ck_pilot_validator_is_synthetic",
        ),
        sa.CheckConstraint(
            "brain_provider IN ('codex','claude')",
            name="ck_pilot_validator_brain_provider",
        ),
        sa.CheckConstraint(
            "review_role IN ('REPRODUCTION_METHODOLOGY','FALSIFICATION_EVIDENCE')",
            name="ck_pilot_validator_review_role",
        ),
    )
    op.create_index(
        "ix_institutional_validators_active",
        "institutional_validators",
        ["active_status", "validator_type"],
    )
    op.create_table(
        "validator_assignments",
        sa.Column("assignment_id", sa.String(30), primary_key=True),
        sa.Column(
            "validator_id",
            sa.String(30),
            sa.ForeignKey("institutional_validators.validator_id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(30),
            sa.ForeignKey("research_candidate_snapshots.candidate_id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("conflict_declaration", sa.Text()),
        sa.Column("commitment_hash", sa.String(64)),
        sa.Column("commitment_signature", sa.String(128)),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.Column("revealed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "validator_id", "candidate_id", name="uq_validator_candidate_assignment"
        ),
    )
    op.create_index(
        "ix_validator_assignments_candidate",
        "validator_assignments",
        ["candidate_id", "state"],
    )
    op.create_table(
        "validator_reviews",
        sa.Column("review_id", sa.String(30), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.String(30),
            sa.ForeignKey("validator_assignments.assignment_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "validator_id",
            sa.String(30),
            sa.ForeignKey("institutional_validators.validator_id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(30),
            sa.ForeignKey("research_candidate_snapshots.candidate_id"),
            nullable=False,
        ),
        sa.Column("verdict", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("reproduction_status", sa.String(64), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("methodology_findings", sa.Text(), nullable=False),
        sa.Column("reproduction_findings", sa.Text(), nullable=False),
        sa.Column("evidence_findings", sa.Text(), nullable=False),
        sa.Column("critical_issues", postgresql.JSONB(), nullable=False),
        sa.Column("minor_issues", postgresql.JSONB(), nullable=False),
        sa.Column("requested_changes", postgresql.JSONB(), nullable=False),
        sa.Column("executed_tests", postgresql.JSONB(), nullable=False),
        sa.Column("artifacts_reviewed", postgresql.JSONB(), nullable=False),
        sa.Column("review_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("genealogy_node_id", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_validator_confidence"),
    )
    op.create_index(
        "ix_validator_reviews_candidate", "validator_reviews", ["candidate_id", "verdict"]
    )


def downgrade() -> None:
    op.drop_table("validator_reviews")
    op.drop_table("validator_assignments")
    op.drop_table("institutional_validators")
    op.drop_constraint("ck_magna_edge_relation", "magna_knowledge_edges", type_="check")
    op.create_check_constraint(
        "ck_magna_edge_relation",
        "magna_knowledge_edges",
        "relation_type IN ('was_derived_from','used','was_generated_by','was_attributed_to',"
        "'supports','refutes','does_not_resolve','replicates','reviews','dissents_from',"
        "'supersedes','depends_on','contradicts','uses','parent_of')",
    )
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
