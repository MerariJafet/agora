"""Persistence model.

Two distinct concepts (ADR-0004):
- `events` is the immutable historical ledger (append-only; DB triggers block
  UPDATE/DELETE — see migration 0001).
- `agents`, `agent_versions`, `devices`, `device_sessions` are current-state
  projections that may be updated.
`event_outbox` is the transactional outbox feeding NATS JetStream.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="registered")
    current_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Additive ownership (ADR-0009/0011). NULL = unowned pre-accounts agent,
    # claimable via the secure pairing flow. Never reassigned implicitly.
    owner_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("users.user_id"), nullable=True
    )
    # Sprint 03: public world identity — cosmetic + semantic only. Nothing
    # here can influence local machine permissions (ADR-0017).
    avatar: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    activity: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")
    activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    card_jws: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class User(Base):
    """Human owner. One owner → many Agents; one Agent → many Devices."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WebSession(Base):
    """Browser owner session: HttpOnly cookie token stored hashed, plus the
    per-session CSRF token for state-changing requests (SEC-012)."""

    __tablename__ = "web_sessions"

    session_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(30), ForeignKey("users.user_id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ClaimChallenge(Base):
    """One-time agent-ownership pairing code (SEC-005): stored hashed,
    short-lived, single-use, bound to (user, agent)."""

    __tablename__ = "claim_challenges"

    claim_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(30), ForeignKey("users.user_id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Space(Base):
    """Public world location. Sprint 02: plaza kind only; kind is the
    extension point for Conversation/Debate/Mission/Arena/Game spaces."""

    __tablename__ = "spaces"

    space_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="plaza")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sprint 04: additive, defaults preserve existing Spaces' behavior.
    evidence_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="optional"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SpaceMessage(Base):
    """Public social message (distinct concept from operational A2A Messages)."""

    __tablename__ = "space_messages"

    message_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    space_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("spaces.space_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String(30), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_messages_space_created", "space_id", "message_id"),)


class ProcessedEvent(Base):
    """Durable consumer idempotency (S2-T01): (consumer, event) uniqueness is
    enforced by the composite primary key at persistence level. Marking and
    the consumer's side effect share one transaction."""

    __tablename__ = "processed_events"

    consumer_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class A2ATask(Base):
    """Operational A2A task relayed between agents (a2a-sdk wire semantics).
    Stores protocol state + artifacts; never private reasoning."""

    __tablename__ = "a2a_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    context_id: Mapped[str] = mapped_column(String(64), nullable=False)
    initiator_agent_id: Mapped[str] = mapped_column(String(30), nullable=False)
    target_agent_id: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="submitted")
    message: Mapped[dict] = mapped_column(JSONB, nullable=False)
    artifacts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    nonce: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_a2a_tasks_target_status", "target_agent_id", "status"),)


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    agent_version_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    public_changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    capabilities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    benchmarks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    signed_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("uq_agent_version_number", "agent_id", "version", unique=True),)


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    public_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="authorized")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RegistrationChallenge(Base):
    __tablename__ = "registration_challenges"

    challenge_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeviceSession(Base):
    """Short-lived session material; only the SHA-256 hash of the token is stored."""

    __tablename__ = "device_sessions"

    session_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("devices.device_id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Event(Base):
    """Immutable public event ledger. Append-only (enforced by DB triggers)."""

    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    causation_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signature: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (Index("ix_events_type_occurred", "event_type", "occurred_at"),)


class EventOutbox(Base):
    """Transactional outbox: written in the same transaction as `events`,
    drained by the NATS publisher. Guarantees state and publication never
    silently diverge (at-least-once delivery; consumers must be idempotent)."""

    __tablename__ = "event_outbox"

    outbox_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("events.event_id"), nullable=False, unique=True
    )
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_outbox_unpublished", "published", "outbox_id"),
    )


class IdempotencyRecord(Base):
    """Registration idempotency: same key returns the original result instead
    of creating a duplicate agent/device."""

    __tablename__ = "idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Sprint 04: Social Intelligence — epistemic domain.
#
# Claims are published-immutable: no route ever exposes UPDATE on their
# semantic content. `status` moves only via retract()/supersede(), which
# append a ledger event in the same transaction as the state change — the
# same pattern as device revocation (ADR-0020).
#
# Evidence is inert provenance metadata; AGORA never fetches `locator`
# (ADR-0021/0024). `provenance_level` is a plain enum column, but every write
# path additionally guards against a client asserting agora_verified_snapshot
# (defense in depth, mirrors the events-table immutability trigger pattern).
# ---------------------------------------------------------------------------


class Claim(Base):
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    space_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("spaces.space_id"), nullable=False
    )
    author_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    author_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    claim_type: Mapped[str] = mapped_column(String(24), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    debate_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    position_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    superseded_by_claim_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_claims_space_created", "space_id", "claim_id"),
        Index("ix_claims_debate", "debate_id"),
        Index("ix_claims_author", "author_agent_id"),
        Index("ix_claims_status", "status"),
    )


class ClaimRelation(Base):
    """Attributed assertion, not a fact of the graph itself: two different
    authors may independently assert the same (source, target, type) edge —
    each is its own row. A given author cannot duplicate their own assertion
    (enforced by a partial unique index in the migration, scoped to active
    rows so a retracted relation can be re-asserted)."""

    __tablename__ = "claim_relations"

    relation_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    source_claim_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("claims.claim_id"), nullable=False
    )
    target_claim_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("claims.claim_id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    author_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_relations_source", "source_claim_id", "status"),
        Index("ix_relations_target", "target_claim_id", "status"),
    )


class Evidence(Base):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    locator: Mapped[str] = mapped_column(String(2048), nullable=False)
    provenance_level: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(String(600), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ClaimEvidence(Base):
    """Attachment: one Evidence object may support/contradict/etc. many
    Claims, and a Claim may cite many Evidence objects."""

    __tablename__ = "claim_evidence"

    attachment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    claim_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("claims.claim_id"), nullable=False
    )
    evidence_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("evidence.evidence_id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    attached_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_claim_evidence_claim", "claim_id"),
        Index("ix_claim_evidence_evidence", "evidence_id"),
    )


class Debate(Base):
    __tablename__ = "debates"

    debate_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    space_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("spaces.space_id"), nullable=False
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    max_participants: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    evidence_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="optional"
    )
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_debates_space", "space_id", "debate_id"),)


class DebatePosition(Base):
    __tablename__ = "debate_positions"

    position_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    debate_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("debates.debate_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_positions_debate", "debate_id"),)


class DebateParticipant(Base):
    """Uniqueness on (debate_id, agent_id) is enforced at the database level
    so a concurrent double-join can never create two rows for one agent; the
    participant-cap race is closed by locking the parent `debates` row before
    counting (see debates_service.join_debate)."""

    __tablename__ = "debate_participants"

    debate_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("debates.debate_id"), primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), primary_key=True
    )
    position_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AudienceAssessment(Base):
    """One CURRENT row per (debate_id, assessor_kind, assessor_id); changes
    while open are upserts, each also appended to the ledger for audit.
    Frozen once the debate closes."""

    __tablename__ = "audience_assessments"

    debate_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("debates.debate_id"), primary_key=True
    )
    assessor_kind: Mapped[str] = mapped_column(String(8), primary_key=True)  # human | agent
    assessor_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    preferred_position_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    evidence_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clarity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    responsiveness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Sprint 05: Missions & Artifacts.
#
# Missions coordinate work through an explicit state machine (ADR-0026):
# a Mission is a social object, NOT an A2A Task or MCP Task — those remain
# transport/execution primitives a MissionTask may use underneath.
#
# Artifacts are content-addressed and immutable once published (ADR-0028):
# ArtifactVersion rows are never updated after creation. Blob bytes live in
# the ArtifactStore (filesystem-backed in Sprint 05), never in Postgres.
# ---------------------------------------------------------------------------


class Mission(Base):
    __tablename__ = "missions"

    mission_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="public")
    hosting_space_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    related_debate_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    related_claim_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    max_participants: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    # Frozen at activation (ADR: completion is evaluated from explicit
    # policy, never coordinator opinion, once active).
    completion_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_by_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    final_artifact_version_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_missions_state", "state"),)


class MissionParticipant(Base):
    """Roles list travels as JSONB: roles are Mission responsibility labels,
    not platform authorization (constitution: roles never grant local
    permissions)."""

    __tablename__ = "mission_participants"

    mission_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("missions.mission_id"), primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), primary_key=True
    )
    agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    roles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MissionTask(Base):
    __tablename__ = "mission_tasks"

    mission_task_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("missions.mission_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    required_skills: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    expected_artifact_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    a2a_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_artifact_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_mission_tasks_mission", "mission_id"),
        Index("ix_mission_tasks_state", "state"),
        Index("ix_mission_tasks_assigned", "assigned_agent_id"),
    )


class MissionTaskDependency(Base):
    """Edge: `task_id` depends on `depends_on_task_id`. Cycle rejection is
    a bounded reachability check at insert time (ADR: Postgres-first graph,
    same posture as the Sprint 04 argument graph — no graph database)."""

    __tablename__ = "mission_task_dependencies"

    task_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("mission_tasks.mission_task_id"), primary_key=True
    )
    depends_on_task_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("mission_tasks.mission_task_id"), primary_key=True
    )


class Artifact(Base):
    """Logical Artifact: mutable display metadata only (title, description,
    visibility). Identity (`artifact_id`) never changes; content lives in
    immutable ArtifactVersion rows."""

    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="public")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    latest_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_artifacts_type", "artifact_type"),)


class ArtifactVersion(Base):
    """Immutable once `state == 'published'`. `state == 'pending'` exists
    only for the brief window between metadata-row creation and blob
    validation completing, so a crash mid-upload never leaves a row that
    LIES about being publish-complete (ADR-0028)."""

    __tablename__ = "artifact_versions"

    artifact_version_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("artifacts.artifact_id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_by_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    display_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    provenance_manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    provenance_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_artifact_versions_artifact", "artifact_id", "version_number", unique=True),
        Index("ix_artifact_versions_hash", "content_hash"),
    )


class ArtifactReview(Base):
    """Append-only: a new review is a new row, never an edit. `is_self_review`
    is computed and stored at creation time so historical reviews keep an
    honest record even if authorship data changes later."""

    __tablename__ = "artifact_reviews"

    review_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    artifact_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("artifact_versions.artifact_version_id"), nullable=False
    )
    reviewer_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_self_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_reviews_version", "artifact_version_id"),)


# ---------------------------------------------------------------------------
# Sprint 06: AGORA Arena.
#
# Arena creates competitive pressure without confusing popularity, points,
# rating, epistemic reputation or truth (ADR-0032). ChallengeVersion freezes
# rules/scoring before play, ScoreEvent is append-only, and leaderboards are
# derived from ScoreEvents rather than hand-edited mutable totals.
# ---------------------------------------------------------------------------


class ArenaSeason(Base):
    __tablename__ = "arena_seasons"

    season_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Challenge(Base):
    __tablename__ = "arena_challenges"

    challenge_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    current_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_arena_challenges_state", "state"),
        Index("ix_arena_challenges_domain", "domain"),
    )


class ChallengeVersion(Base):
    __tablename__ = "arena_challenge_versions"

    challenge_version_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    challenge_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("arena_challenges.challenge_id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    complexity: Mapped[dict] = mapped_column(JSONB, nullable=False)
    certified_difficulty: Mapped[float] = mapped_column(Float, nullable=False)
    verifier_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scoring_formula: Mapped[dict] = mapped_column(JSONB, nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ix_arena_challenge_versions_challenge",
            "challenge_id",
            "version_number",
            unique=True,
        ),
    )


class ChallengeInstance(Base):
    __tablename__ = "arena_challenge_instances"

    challenge_instance_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    challenge_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("arena_challenges.challenge_id"), nullable=False
    )
    challenge_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("arena_challenge_versions.challenge_version_id"),
        nullable=False,
    )
    season_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    max_participants: Mapped[int] = mapped_column(Integer, nullable=False, default=16)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_arena_instances_state", "state"),
        Index("ix_arena_instances_challenge", "challenge_id"),
    )


class ChallengeParticipant(Base):
    __tablename__ = "arena_participants"

    challenge_instance_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("arena_challenge_instances.challenge_instance_id"),
        primary_key=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), primary_key=True
    )
    owner_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Submission(Base):
    __tablename__ = "arena_submissions"

    submission_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    challenge_instance_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("arena_challenge_instances.challenge_instance_id"),
        nullable=False,
    )
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    answer: Mapped[dict] = mapped_column(JSONB, nullable=False)
    artifact_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("challenge_instance_id", "agent_id", name="uq_arena_submission_agent"),
        Index("ix_arena_submissions_instance", "challenge_instance_id"),
    )


class Judgment(Base):
    __tablename__ = "arena_judgments"

    judgment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    submission_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("arena_submissions.submission_id"), nullable=False
    )
    judge_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    judge_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    correctness: Mapped[float | None] = mapped_column(Float, nullable=True)
    audience_preference: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_arena_judgments_submission", "submission_id"),)


class ScoreEvent(Base):
    __tablename__ = "arena_score_events"

    score_event_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    challenge_instance_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("arena_challenge_instances.challenge_instance_id"),
        nullable=False,
    )
    submission_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("arena_submissions.submission_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    score_delta: Mapped[float] = mapped_column(Float, nullable=False)
    rating_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    formula_version: Mapped[str] = mapped_column(String(16), nullable=False)
    factors: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("submission_id", name="uq_arena_score_submission"),
        Index("ix_arena_score_events_agent", "agent_id"),
        Index("ix_arena_score_events_instance", "challenge_instance_id"),
    )


class ArenaRating(Base):
    __tablename__ = "arena_ratings"

    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), primary_key=True
    )
    domain: Mapped[str] = mapped_column(String(64), primary_key=True)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=1500.0)
    rating_deviation: Mapped[float] = mapped_column(Float, nullable=False, default=350.0)
    points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Sprint 07: Live Knowledge Fabric.
#
# Knowledge adapters are controlled source boundaries, not a generic crawler.
# Snapshots are immutable public-source observations with freshness, license,
# source metadata and content hashes. Evidence can become
# `agora_verified_snapshot` only by referencing one of these snapshots.
# ---------------------------------------------------------------------------


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    source_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    adapter_id: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(300), nullable=False)
    allowed_hosts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    capabilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    freshness_contract: Mapped[str] = mapped_column(String(24), nullable=False)
    license_terms: Mapped[str] = mapped_column(String(300), nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    upstream_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                                nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_knowledge_sources_domain", "domain"),
        Index("ix_knowledge_sources_enabled", "enabled"),
    )


class KnowledgeSnapshot(Base):
    __tablename__ = "knowledge_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("knowledge_sources.source_id"), nullable=False
    )
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(400), nullable=False)
    query: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_locator: Mapped[str] = mapped_column(String(500), nullable=False)
    freshness_contract: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                               nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    license_terms: Mapped[str] = mapped_column(String(300), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_knowledge_snapshots_source_query", "source_id", "query_hash"),
        Index("ix_knowledge_snapshots_hash", "content_hash"),
    )


class WorldPulseEvent(Base):
    __tablename__ = "world_pulse_events"

    pulse_event_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    cluster_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    summary: Mapped[str] = mapped_column(String(800), nullable=False)
    freshness_contract: Mapped[str] = mapped_column(String(24), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latest_snapshot_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("knowledge_snapshots.snapshot_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_world_pulse_events_updated", "updated_at"),)


class WorldPulseSource(Base):
    __tablename__ = "world_pulse_sources"

    pulse_event_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("world_pulse_events.pulse_event_id"), primary_key=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("knowledge_snapshots.snapshot_id"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("knowledge_sources.source_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Sprint 08: Games, Modules & World Builder.
#
# Modules are declarative AGORA world extensions. Capability grants are
# platform/module capabilities only; they never become local device permissions.
# Runtime state is persistent semantic state, not server-side animation.
# ---------------------------------------------------------------------------


class Module(Base):
    __tablename__ = "modules"

    module_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    current_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rollback_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_modules_state", "state"),)


class ModuleVersion(Base):
    __tablename__ = "module_versions"

    module_version_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    module_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("modules.module_id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    game_manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    static_analysis: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    resource_estimate: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_module_versions_module", "module_id", "version_number", unique=True),
        Index("ix_module_versions_state", "state"),
    )


class Game(Base):
    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    module_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("modules.module_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="experimental")
    current_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GameVersion(Base):
    __tablename__ = "game_versions"

    game_version_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    game_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("games.game_id"), nullable=False
    )
    module_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("module_versions.module_version_id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    game_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GameSession(Base):
    __tablename__ = "game_sessions"

    game_session_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    game_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("game_versions.game_version_id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="lobby")
    session_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_by_agent_id: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorldPlot(Base):
    __tablename__ = "world_plots"

    plot_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="empty")
    runtime_state: Mapped[str] = mapped_column(String(16), nullable=False, default="cold")
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    radius: Mapped[int] = mapped_column(Integer, nullable=False)
    module_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    active_lease_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_world_plots_state", "state", "runtime_state"),)


class ResourceLease(Base):
    __tablename__ = "resource_leases"

    lease_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    plot_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("world_plots.plot_id"), nullable=False
    )
    module_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("modules.module_id"), nullable=False
    )
    owner_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    resource_estimate: Mapped[dict] = mapped_column(JSONB, nullable=False)
    credits_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BuildProposal(Base):
    __tablename__ = "build_proposals"

    proposal_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    module_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("modules.module_id"), nullable=False
    )
    module_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("module_versions.module_version_id"), nullable=False
    )
    proposed_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    target_plot_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    pipeline: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_build_proposals_state", "state"),)


class ModuleReview(Base):
    __tablename__ = "module_reviews"

    review_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    module_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("module_versions.module_version_id"), nullable=False
    )
    reviewer_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    security_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("module_version_id", "reviewer_agent_id",
                         name="uq_module_review_version_reviewer"),
    )


class CapabilityGrant(Base):
    __tablename__ = "capability_grants"

    grant_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    module_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("module_versions.module_version_id"), nullable=False
    )
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    granted_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# Sprint 09: Civic Intelligence, Replay, Evolution & Governance.
#
# Civic agents are normal agents with public roles/subscriptions; their outputs
# are auditable artifacts/findings, not central control. Replay is read-only
# over the Event Ledger and never re-executes effects. Agent evolution is
# versioned, benchmark-attributed and reversible.
# ---------------------------------------------------------------------------


class CivicRoleManifest(Base):
    __tablename__ = "civic_role_manifests"

    role_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_civic_roles_role", "role", "status"),)


class CivicSubscription(Base):
    __tablename__ = "civic_subscriptions"

    subscription_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    role_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("civic_role_manifests.role_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    filters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_civic_subscriptions_agent", "agent_id", "status"),
        UniqueConstraint("role_id", "agent_id", "scope", name="uq_civic_subscription_scope"),
    )


class SummaryArtifact(Base):
    __tablename__ = "summary_artifacts"

    summary_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    artifact_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    coverage_event_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    snapshot_start_event_id: Mapped[str] = mapped_column(String(30), nullable=False)
    snapshot_end_event_id: Mapped[str] = mapped_column(String(30), nullable=False)
    source_pointers: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    explicit_uncertainty: Mapped[str] = mapped_column(Text, nullable=False)
    creator_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    creator_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    disagreement_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_summary_range", "snapshot_start_event_id", "snapshot_end_event_id"),
    )


class CivicFinding(Base):
    __tablename__ = "civic_findings"

    finding_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    finding_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    related_claim_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    related_evidence_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    related_snapshot_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    summary_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_civic_findings_type", "finding_type", "created_at"),)


class ReplayRun(Base):
    __tablename__ = "replay_runs"

    replay_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    start_event_id: Mapped[str] = mapped_column(String(30), nullable=False)
    end_event_id: Mapped[str] = mapped_column(String(30), nullable=False)
    speed: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ForgeRFC(Base):
    __tablename__ = "forge_rfcs"

    rfc_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    proposal: Mapped[str] = mapped_column(Text, nullable=False)
    test_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    discussion_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_forge_rfcs_status", "status", "created_at"),)


class ImprovementProposal(Base):
    __tablename__ = "improvement_proposals"

    proposal_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_change: Mapped[str] = mapped_column(Text, nullable=False)
    benchmark: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    rollback: Mapped[str] = mapped_column(Text, nullable=False)
    owner_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_improvement_agent", "agent_id", "status"),)


class AgentVersionActivation(Base):
    __tablename__ = "agent_version_activations"

    activation_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    from_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_agent_version_id: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReputationEvent(Base):
    __tablename__ = "reputation_events"

    reputation_event_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_reputation_agent_dimension", "agent_id", "dimension"),)


class SkillPassport(Base):
    __tablename__ = "skill_passports"

    passport_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    skill: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_refs: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_skill_passport_agent", "agent_id", "skill"),
        UniqueConstraint("agent_id", "skill", "source_kind", name="uq_skill_passport_kind"),
    )


# ---------------------------------------------------------------------------
# Sprint 10: Hardening & Public Alpha.
#
# These are operational safety surfaces. They do not deploy externally, do not
# introduce privileged scientific reputation, and do not require credentials.
# ---------------------------------------------------------------------------


class ModerationReport(Base):
    __tablename__ = "moderation_reports"

    report_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    evidence_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    reporter_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_moderation_reports_status", "status", "severity"),)


class AdminAction(Base):
    __tablename__ = "admin_actions"

    action_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    actor_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    report_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reputation_effect: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_admin_actions_target", "target_type", "target_id"),)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    flag_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    key: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AlphaFeedback(Base):
    __tablename__ = "alpha_feedback"

    feedback_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reporter_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_alpha_feedback_category", "category", "status"),)


class DrillRun(Base):
    __tablename__ = "drill_runs"

    drill_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    drill_type: Mapped[str] = mapped_column(String(48), nullable=False)
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    safe_simulation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
