"""Forum-centered research consensus.

Revision ID: 0027_forum_consensus
Revises: 0026_magna_private
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_forum_consensus"
down_revision = "0026_magna_private"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forums",
        sa.Column("forum_id", sa.String(30), primary_key=True),
        sa.Column("forum_type", sa.String(40), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "forum_type IN ('WORLD_FORUM','DISTRICT_FORUM','RESEARCH_SELECTION_FORUM',"
            "'CHALLENGE_ROOM','OPEN_GROUP','INVITE_GROUP','DIRECT_THREAD','REVIEW_PANEL')",
            name="ck_forum_type",
        ),
        sa.CheckConstraint(
            "visibility IN ('PUBLIC','PUBLIC_JOINABLE','MEMBERS_ONLY',"
            "'TWO_PARTY','PUBLIC_RESULTS')",
            name="ck_forum_visibility",
        ),
        sa.CheckConstraint("state IN ('open','closed','archived')", name="ck_forum_state"),
        sa.UniqueConstraint("forum_type", "scope_id", name="uq_forum_type_scope"),
    )
    op.create_index("ix_forums_type_state", "forums", ["forum_type", "state"])

    op.create_table(
        "forum_threads",
        sa.Column("thread_id", sa.String(30), primary_key=True),
        sa.Column("forum_id", sa.String(30), sa.ForeignKey("forums.forum_id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_by_agent_id", sa.String(30), nullable=True),
        sa.Column("thread_metadata", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("state IN ('open','closed','archived')", name="ck_forum_thread_state"),
        sa.UniqueConstraint("forum_id", "title", name="uq_forum_thread_title"),
    )
    op.create_index("ix_forum_threads_forum", "forum_threads", ["forum_id", "state"])

    op.create_table(
        "forum_posts",
        sa.Column("post_id", sa.String(30), primary_key=True),
        sa.Column("forum_id", sa.String(30), sa.ForeignKey("forums.forum_id"), nullable=False),
        sa.Column(
            "thread_id", sa.String(30), sa.ForeignKey("forum_threads.thread_id"), nullable=False
        ),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.String(30), sa.ForeignKey("events.event_id"), nullable=True),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("actor_agent_id", sa.String(30), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parent_post_id", sa.String(30), nullable=True),
        sa.Column("post_metadata", postgresql.JSONB, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("actor_kind IN ('system','agent','human')", name="ck_forum_post_actor"),
        sa.UniqueConstraint("forum_id", "sequence", name="uq_forum_post_sequence"),
        sa.UniqueConstraint("thread_id", "content_hash", name="uq_forum_thread_content_hash"),
    )
    op.create_index(
        "ix_forum_posts_thread_sequence", "forum_posts", ["thread_id", "sequence"]
    )
    op.create_index("ix_forum_posts_event", "forum_posts", ["event_id"])

    op.create_table(
        "forum_delivery_receipts",
        sa.Column("receipt_id", sa.String(30), primary_key=True),
        sa.Column("event_id", sa.String(30), sa.ForeignKey("events.event_id"), nullable=False),
        sa.Column("forum_id", sa.String(30), sa.ForeignKey("forums.forum_id"), nullable=False),
        sa.Column(
            "thread_id", sa.String(30), sa.ForeignKey("forum_threads.thread_id"), nullable=False
        ),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("delivery_state", sa.String(16), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "delivery_state IN ('queued','delivered','seen','failed')",
            name="ck_forum_delivery_state",
        ),
        sa.UniqueConstraint("event_id", "agent_id", name="uq_forum_delivery_event_agent"),
    )
    op.create_index(
        "ix_forum_delivery_agent_sequence",
        "forum_delivery_receipts",
        ["agent_id", "sequence"],
    )
    op.create_index(
        "ix_forum_delivery_forum_state",
        "forum_delivery_receipts",
        ["forum_id", "delivery_state"],
    )

    op.create_table(
        "research_consensus_rounds",
        sa.Column("round_id", sa.String(30), primary_key=True),
        sa.Column("world_instance_id", sa.String(64), nullable=False),
        sa.Column("forum_id", sa.String(30), sa.ForeignKey("forums.forum_id"), nullable=False),
        sa.Column(
            "thread_id", sa.String(30), sa.ForeignKey("forum_threads.thread_id"), nullable=False
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("eligible_voter_agent_ids", postgresql.JSONB, nullable=False),
        sa.Column("proposal_ids", postgresql.JSONB, nullable=False),
        sa.Column("selected_proposal_id", sa.String(30), nullable=True),
        sa.Column("countdown_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rules_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposal_window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deliberation_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("voting_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consensus_result", sa.String(32), nullable=True),
        sa.Column("quorum_count", sa.Integer(), nullable=False),
        sa.Column("approval_count", sa.Integer(), nullable=False),
        sa.Column("reject_count", sa.Integer(), nullable=False),
        sa.Column("abstain_count", sa.Integer(), nullable=False),
        sa.Column("needs_revision_count", sa.Integer(), nullable=False),
        sa.Column("reward_aceros", sa.BigInteger(), nullable=False),
        sa.Column("reward_reserved", sa.Boolean(), nullable=False),
        sa.Column("challenge_mission_id", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('scheduled','proposal_window','deliberation','voting',"
            "'complete_no_consensus','complete_consensus','interrupted')",
            name="ck_research_round_state",
        ),
        sa.CheckConstraint("reward_aceros >= 0", name="ck_research_round_reward"),
        sa.UniqueConstraint("world_instance_id", "title", name="uq_research_round_world_title"),
    )
    op.create_index("ix_research_round_state", "research_consensus_rounds", ["state"])

    op.create_table(
        "research_votes",
        sa.Column("vote_id", sa.String(30), primary_key=True),
        sa.Column(
            "round_id",
            sa.String(30),
            sa.ForeignKey("research_consensus_rounds.round_id"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column(
            "proposal_id",
            sa.String(30),
            sa.ForeignKey("research_proposals.proposal_id"),
            nullable=True,
        ),
        sa.Column("vote", sa.String(16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "vote IN ('APPROVE','REJECT','ABSTAIN','NEEDS_REVISION')",
            name="ck_research_vote_value",
        ),
        sa.UniqueConstraint("round_id", "agent_id", name="uq_research_vote_round_agent"),
        sa.UniqueConstraint("agent_id", "idempotency_key", name="uq_research_vote_idem"),
    )
    op.create_index("ix_research_votes_round_vote", "research_votes", ["round_id", "vote"])


def downgrade() -> None:
    op.drop_index("ix_research_votes_round_vote", table_name="research_votes")
    op.drop_table("research_votes")
    op.drop_index("ix_research_round_state", table_name="research_consensus_rounds")
    op.drop_table("research_consensus_rounds")
    op.drop_index("ix_forum_delivery_forum_state", table_name="forum_delivery_receipts")
    op.drop_index("ix_forum_delivery_agent_sequence", table_name="forum_delivery_receipts")
    op.drop_table("forum_delivery_receipts")
    op.drop_index("ix_forum_posts_event", table_name="forum_posts")
    op.drop_index("ix_forum_posts_thread_sequence", table_name="forum_posts")
    op.drop_table("forum_posts")
    op.drop_index("ix_forum_threads_forum", table_name="forum_threads")
    op.drop_table("forum_threads")
    op.drop_index("ix_forums_type_state", table_name="forums")
    op.drop_table("forums")
