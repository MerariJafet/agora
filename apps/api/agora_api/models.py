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
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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
