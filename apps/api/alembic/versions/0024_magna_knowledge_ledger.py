"""MAGNA Sprint 03 knowledge ledger.

Revision ID: 0024_magna_knowledge_ledger
Revises: 0023_magna_research_allocation
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_magna_knowledge_ledger"
down_revision: str | None = "0023_magna_research_allocation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OBJECT_TYPES = (
    "'research_question','hypothesis','claim','method','registered_protocol',"
    "'protocol_amendment','dataset','artifact_version','experiment_run','evidence',"
    "'contribution','replication_plan','replication','review','dissent','outcome',"
    "'reproducibility_capsule','validation_package'"
)
RELATION_TYPES = (
    "'was_derived_from','used','was_generated_by','was_attributed_to','supports',"
    "'refutes','does_not_resolve','replicates','reviews','dissents_from','supersedes',"
    "'depends_on'"
)
EPISTEMIC_STATES = (
    "'PROPOSED','UNDER_TEST','SUPPORTED_ONCE','REPLICATED','CONTESTED','REFUTED',"
    "'INCONCLUSIVE','SUPERSEDED'"
)


def upgrade() -> None:
    op.create_table(
        "magna_knowledge_objects",
        sa.Column("object_id", sa.String(length=30), primary_key=True),
        sa.Column("object_type", sa.String(length=40), nullable=False),
        sa.Column("object_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=40), nullable=True),
        sa.Column("challenge_id", sa.String(length=30), nullable=True),
        sa.Column("proposal_id", sa.String(length=30), nullable=True),
        sa.Column(
            "author_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("author_agent_version_id", sa.String(length=30), nullable=True),
        sa.Column("beneficial_controller_id", sa.String(length=120), nullable=False),
        sa.Column("visibility_lane", sa.String(length=16), nullable=False),
        sa.Column("safety_classification", sa.String(length=64), nullable=False),
        sa.Column("rights_status", sa.String(length=32), nullable=False),
        sa.Column("license_id", sa.String(length=80), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "public_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("canonical_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "parent_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("constitution_hash", sa.String(length=64), nullable=False),
        sa.Column("charter_hash", sa.String(length=64), nullable=True),
        sa.Column("rule_evaluation_receipt_id", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="PROPOSED"),
        sa.Column("maturity", sa.String(length=32), nullable=False, server_default="exploratory"),
        sa.Column("frozen_hash", sa.String(length=64), nullable=True),
        sa.Column("supersedes_object_id", sa.String(length=30), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"object_type IN ({OBJECT_TYPES})", name="ck_magna_object_type"),
        sa.CheckConstraint(
            "visibility_lane IN ('OPEN','SEALED','RESTRICTED')", name="ck_magna_lane"
        ),
        sa.CheckConstraint(
            "rights_status IN ("
            "'explicit_open_license','pending_human_review','restricted','unknown'"
            ")",
            name="ck_magna_rights_status",
        ),
        sa.CheckConstraint(f"state IN ({EPISTEMIC_STATES})", name="ck_magna_object_state"),
        sa.CheckConstraint(
            "maturity IN ('exploratory','internally_validated','externally_reproduced')",
            name="ck_magna_maturity",
        ),
        sa.UniqueConstraint("author_agent_id", "idempotency_key", name="uq_magna_object_idem"),
        sa.UniqueConstraint("canonical_content_hash", name="uq_magna_object_hash"),
    )
    op.create_index(
        "ix_magna_objects_type_state", "magna_knowledge_objects", ["object_type", "state"]
    )
    op.create_index(
        "ix_magna_objects_world_lane", "magna_knowledge_objects", ["world_id", "visibility_lane"]
    )
    op.create_index("ix_magna_objects_proposal", "magna_knowledge_objects", ["proposal_id"])
    op.create_index("ix_magna_objects_challenge", "magna_knowledge_objects", ["challenge_id"])

    op.create_table(
        "magna_knowledge_edges",
        sa.Column("edge_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "source_object_id",
            sa.String(length=30),
            sa.ForeignKey("magna_knowledge_objects.object_id"),
            nullable=False,
        ),
        sa.Column(
            "target_object_id",
            sa.String(length=30),
            sa.ForeignKey("magna_knowledge_objects.object_id"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
        sa.Column(
            "actor_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("actor_agent_version_id", sa.String(length=30), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("canonical_content_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"relation_type IN ({RELATION_TYPES})", name="ck_magna_edge_relation"),
        sa.CheckConstraint("source_object_id <> target_object_id", name="ck_magna_no_self_edge"),
        sa.UniqueConstraint("actor_agent_id", "idempotency_key", name="uq_magna_edge_idem"),
        sa.UniqueConstraint(
            "source_object_id",
            "target_object_id",
            "relation_type",
            "actor_agent_id",
            name="uq_magna_edge_assertion",
        ),
    )
    op.create_index(
        "ix_magna_edges_source", "magna_knowledge_edges", ["source_object_id", "relation_type"]
    )
    op.create_index(
        "ix_magna_edges_target", "magna_knowledge_edges", ["target_object_id", "relation_type"]
    )

    op.create_table(
        "magna_resolution_receipts",
        sa.Column("receipt_id", sa.String(length=30), primary_key=True),
        sa.Column("challenge_id", sa.String(length=30), nullable=False),
        sa.Column(
            "outcome_id",
            sa.String(length=30),
            sa.ForeignKey("magna_knowledge_objects.object_id"),
            nullable=False,
        ),
        sa.Column(
            "registered_protocol_id",
            sa.String(length=30),
            sa.ForeignKey("magna_knowledge_objects.object_id"),
            nullable=False,
        ),
        sa.Column("requested_state", sa.String(length=24), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_object_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "replication_object_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("review_object_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "unresolved_dissent_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("independence_receipt", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("constitution_hash", sa.String(length=64), nullable=False),
        sa.Column("charter_hash", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "payment_eligible", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_by_agent_id",
            sa.String(length=30),
            sa.ForeignKey("agents.agent_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"requested_state IN ({EPISTEMIC_STATES})", name="ck_magna_receipt_state"
        ),
        sa.CheckConstraint("decision IN ('accepted','rejected')", name="ck_magna_receipt_decision"),
        sa.UniqueConstraint("content_hash", name="uq_magna_receipt_hash"),
        sa.UniqueConstraint("created_by_agent_id", "idempotency_key", name="uq_magna_receipt_idem"),
    )
    op.create_index(
        "ix_magna_receipts_challenge", "magna_resolution_receipts", ["challenge_id", "decision"]
    )

    op.create_table(
        "magna_merkle_batches",
        sa.Column("batch_id", sa.String(length=30), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("first_sequence", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("leaf_count", sa.Integer(), nullable=False),
        sa.Column("merkle_root", sa.String(length=64), nullable=False),
        sa.Column(
            "algorithm", sa.String(length=32), nullable=False, server_default="sha256-binary-tree"
        ),
        sa.Column("previous_batch_hash", sa.String(length=64), nullable=True),
        sa.Column("leaves", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_agent_id", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("first_sequence <= last_sequence", name="ck_magna_merkle_window"),
        sa.CheckConstraint("leaf_count > 0", name="ck_magna_merkle_nonempty"),
        sa.UniqueConstraint(
            "world_instance_id",
            "first_sequence",
            "last_sequence",
            name="uq_magna_merkle_window",
        ),
    )
    op.create_index(
        "ix_magna_merkle_world", "magna_merkle_batches", ["world_instance_id", "last_sequence"]
    )

    op.create_table(
        "magna_publication_decisions",
        sa.Column("decision_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "object_id",
            sa.String(length=30),
            sa.ForeignKey("magna_knowledge_objects.object_id"),
            nullable=False,
        ),
        sa.Column("requested_lane", sa.String(length=16), nullable=False),
        sa.Column("decided_lane", sa.String(length=16), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("rights_receipt", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("safety_receipt", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "human_authority_required", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_by_agent_id", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_magna_publication_object", "magna_publication_decisions", ["object_id"])

    op.create_table(
        "magna_access_grants",
        sa.Column("grant_id", sa.String(length=30), primary_key=True),
        sa.Column(
            "object_id",
            sa.String(length=30),
            sa.ForeignKey("magna_knowledge_objects.object_id"),
            nullable=False,
        ),
        sa.Column("grantee_type", sa.String(length=24), nullable=False),
        sa.Column("grantee_id", sa.String(length=80), nullable=False),
        sa.Column("purpose", sa.String(length=80), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_agent_id", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_magna_access_object_grantee",
        "magna_access_grants",
        ["object_id", "grantee_id", "state"],
    )


def downgrade() -> None:
    op.drop_index("ix_magna_access_object_grantee", table_name="magna_access_grants")
    op.drop_table("magna_access_grants")
    op.drop_index("ix_magna_publication_object", table_name="magna_publication_decisions")
    op.drop_table("magna_publication_decisions")
    op.drop_index("ix_magna_merkle_world", table_name="magna_merkle_batches")
    op.drop_table("magna_merkle_batches")
    op.drop_index("ix_magna_receipts_challenge", table_name="magna_resolution_receipts")
    op.drop_table("magna_resolution_receipts")
    op.drop_index("ix_magna_edges_target", table_name="magna_knowledge_edges")
    op.drop_index("ix_magna_edges_source", table_name="magna_knowledge_edges")
    op.drop_table("magna_knowledge_edges")
    op.drop_index("ix_magna_objects_challenge", table_name="magna_knowledge_objects")
    op.drop_index("ix_magna_objects_proposal", table_name="magna_knowledge_objects")
    op.drop_index("ix_magna_objects_world_lane", table_name="magna_knowledge_objects")
    op.drop_index("ix_magna_objects_type_state", table_name="magna_knowledge_objects")
    op.drop_table("magna_knowledge_objects")
