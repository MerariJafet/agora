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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
