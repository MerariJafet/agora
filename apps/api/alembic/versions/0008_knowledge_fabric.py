"""Sprint 07 Knowledge Fabric: sources, snapshots and World Pulse.

Revision ID: 0008
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


SOURCES = [
    (
        "kso_00000000000000000000000001", "openalex", "OpenAlex", "literature",
        "https://api.openalex.org", ["api.openalex.org"], ["search", "fetch", "snapshot"],
        "DAILY", "OpenAlex metadata license/terms as published by source.", 86400,
    ),
    (
        "kso_00000000000000000000000002", "crossref", "Crossref", "literature",
        "https://api.crossref.org", ["api.crossref.org"], ["search", "fetch", "snapshot"],
        "DAILY", "Crossref metadata terms as published by source.", 86400,
    ),
    (
        "kso_00000000000000000000000003", "clinvar", "ClinVar", "genetics",
        "https://eutils.ncbi.nlm.nih.gov", ["eutils.ncbi.nlm.nih.gov"],
        ["search", "fetch", "snapshot"], "WEEKLY",
        "NCBI ClinVar public metadata terms.", 604800,
    ),
    (
        "kso_00000000000000000000000004", "ensembl", "Ensembl", "genetics",
        "https://rest.ensembl.org", ["rest.ensembl.org"], ["search", "fetch", "snapshot"],
        "WEEKLY", "Ensembl public API terms.", 604800,
    ),
    (
        "kso_00000000000000000000000005", "fred", "FRED", "economy",
        "https://api.stlouisfed.org", ["api.stlouisfed.org"],
        ["search", "fetch", "snapshot", "time_series"], "DAILY",
        "FRED source metadata terms; vintages are represented when supplied.", 86400,
    ),
    (
        "kso_00000000000000000000000006", "world_bank", "World Bank", "economy",
        "https://api.worldbank.org", ["api.worldbank.org"],
        ["search", "fetch", "snapshot", "time_series"], "DAILY",
        "World Bank API terms and licenses as published by source.", 86400,
    ),
    (
        "kso_00000000000000000000000007", "gdelt_world_pulse", "GDELT World Pulse",
        "world_pulse", "https://api.gdeltproject.org", ["api.gdeltproject.org"],
        ["search", "fetch", "snapshot", "event_cluster"], "NEAR_REALTIME",
        "GDELT metadata/source terms; article text is not replicated.", 900,
    ),
    (
        "kso_00000000000000000000000008", "nasa_public", "NASA Public Data",
        "space_science", "https://api.nasa.gov", ["api.nasa.gov"],
        ["search", "fetch", "snapshot", "event_cluster"], "DAILY",
        "NASA public metadata terms; dataset contents are referenced, not copied.", 86400,
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO spaces (space_id, slug, name, kind, description, created_at) "
            "VALUES (:sid, :slug, :name, 'knowledge', :descr, NOW()) "
            "ON CONFLICT (space_id) DO UPDATE SET slug = EXCLUDED.slug, "
            "name = EXCLUDED.name, kind = EXCLUDED.kind, description = EXCLUDED.description"
        ),
        {
            "sid": "spc_00000000000000000000PULSE",
            "slug": "world-pulse",
            "name": "World Pulse",
            "descr": "Clustered public-source events with freshness and provenance.",
        },
    )

    op.create_table(
        "knowledge_sources",
        sa.Column("source_id", sa.String(30), primary_key=True),
        sa.Column("adapter_id", sa.String(48), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(300), nullable=False),
        sa.Column("allowed_hosts", JSONB, nullable=False),
        sa.Column("capabilities", JSONB, nullable=False),
        sa.Column("freshness_contract", sa.String(24), nullable=False),
        sa.Column("license_terms", sa.String(300), nullable=False),
        sa.Column("ttl_seconds", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("upstream_call_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_hit_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("circuit_open_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_sources_domain", "knowledge_sources", ["domain"])
    op.create_index("ix_knowledge_sources_enabled", "knowledge_sources", ["enabled"])

    op.create_table(
        "knowledge_snapshots",
        sa.Column("snapshot_id", sa.String(30), primary_key=True),
        sa.Column("source_id", sa.String(30), sa.ForeignKey("knowledge_sources.source_id"),
                  nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("normalized_query", sa.String(400), nullable=False),
        sa.Column("query", JSONB, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("raw_metadata", JSONB, nullable=False),
        sa.Column("raw_locator", sa.String(500), nullable=False),
        sa.Column("freshness_contract", sa.String(24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("license_terms", sa.String(300), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_snapshots_source_query", "knowledge_snapshots",
                    ["source_id", "query_hash"])
    op.create_index("ix_knowledge_snapshots_hash", "knowledge_snapshots", ["content_hash"])

    op.create_table(
        "world_pulse_events",
        sa.Column("pulse_event_id", sa.String(30), primary_key=True),
        sa.Column("cluster_key", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(220), nullable=False),
        sa.Column("summary", sa.String(800), nullable=False),
        sa.Column("freshness_contract", sa.String(24), nullable=False),
        sa.Column("source_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("latest_snapshot_id", sa.String(30),
                  sa.ForeignKey("knowledge_snapshots.snapshot_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_world_pulse_events_updated", "world_pulse_events", ["updated_at"])

    op.create_table(
        "world_pulse_sources",
        sa.Column("pulse_event_id", sa.String(30),
                  sa.ForeignKey("world_pulse_events.pulse_event_id"), primary_key=True),
        sa.Column("snapshot_id", sa.String(30),
                  sa.ForeignKey("knowledge_snapshots.snapshot_id"), primary_key=True),
        sa.Column("source_id", sa.String(30), sa.ForeignKey("knowledge_sources.source_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    for source in SOURCES:
        bind.execute(
            sa.text(
                "INSERT INTO knowledge_sources "
                "(source_id, adapter_id, name, domain, base_url, allowed_hosts, capabilities, "
                "freshness_contract, license_terms, ttl_seconds, enabled, created_at, updated_at) "
                "VALUES (:source_id, :adapter_id, :name, :domain, :base_url, "
                "CAST(:allowed_hosts AS jsonb), CAST(:capabilities AS jsonb), "
                ":freshness_contract, :license_terms, :ttl_seconds, true, NOW(), NOW())"
            ),
            {
                "source_id": source[0],
                "adapter_id": source[1],
                "name": source[2],
                "domain": source[3],
                "base_url": source[4],
                "allowed_hosts": json.dumps(source[5]),
                "capabilities": json.dumps(source[6]),
                "freshness_contract": source[7],
                "license_terms": source[8],
                "ttl_seconds": source[9],
            },
        )


def downgrade() -> None:
    op.drop_table("world_pulse_sources")
    op.drop_table("world_pulse_events")
    op.drop_table("knowledge_snapshots")
    op.drop_index("ix_knowledge_sources_enabled", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_domain", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
    op.execute(sa.text("DELETE FROM spaces WHERE space_id = 'spc_00000000000000000000PULSE'"))
