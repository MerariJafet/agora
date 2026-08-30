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


class AgentIdentityMetadata(Base):
    """World-facing identity metadata separated from cryptographic identity.

    `agents.agent_id` remains the only ownership/authentication key. Everything
    here is presentation or operational metadata with explicit assurance.
    """

    __tablename__ = "agent_identity_metadata"

    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), primary_key=True
    )
    canonical_name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(96), nullable=True)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    runtime_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_assurance: Mapped[str] = mapped_column(String(32), nullable=False, default="db")
    metadata_conflict: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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
    evidence_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="optional")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SpaceMessage(Base):
    """Public social message (distinct concept from operational A2A Messages)."""

    __tablename__ = "space_messages"

    message_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    space_id: Mapped[str] = mapped_column(String(30), ForeignKey("spaces.space_id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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


class DeviceInstallationKey(Base):
    """Privacy-preserving local installation continuity record.

    The value is an owner/Bridge-generated public key, not a hardware
    fingerprint. AGORA never stores MAC, disk serial, machine-id, TPM
    endorsement keys or raw hardware identifiers.
    """

    __tablename__ = "device_installation_keys"

    installation_key_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("devices.device_id"), nullable=False, unique=True
    )
    public_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentGenesis(Base):
    """Canonical one-time birth record for an Agent ID."""

    __tablename__ = "agent_genesis"

    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), primary_key=True
    )
    genesis_event_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("events.event_id"), nullable=False, unique=True
    )
    first_device_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("devices.device_id"), nullable=False
    )
    agent_public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    device_public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    born_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentDeviceAuthorization(Base):
    """Agent↔device authorization projection.

    A device can authenticate itself, but whether that device is ordinary,
    pending, revoked or recovery-authorized for an Agent is tracked here.
    """

    __tablename__ = "agent_device_authorizations"

    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), primary_key=True
    )
    device_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("devices.device_id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="authorized")
    assurance_level: Mapped[str] = mapped_column(String(24), nullable=False, default="device")
    authorized_by_device_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_agent_device_authorizations_device", "device_id"),)


class EnrollmentChallenge(Base):
    """Short-lived challenge for lineage/passport enrollment.

    This is separate from initial registration because it binds an existing
    Agent ID, Device ID, constitution hash and nonce.
    """

    __tablename__ = "enrollment_challenges"

    challenge_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    device_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("devices.device_id"), nullable=False
    )
    nonce: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_enrollment_challenges_agent_device", "agent_id", "device_id"),)


class AgentKeyRotation(Base):
    __tablename__ = "agent_key_rotations"

    rotation_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    device_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("devices.device_id"), nullable=False
    )
    old_public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    new_public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    rotation_event_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_agent_key_rotations_agent", "agent_id"),
        UniqueConstraint("agent_id", "new_public_key", name="uq_agent_rotation_new_key"),
    )


class PassportSession(Base):
    """Short-lived signed passport material stored by digest only."""

    __tablename__ = "passport_sessions"

    passport_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    device_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("devices.device_id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    assurance_level: Mapped[str] = mapped_column(String(24), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_passport_sessions_agent_device", "agent_id", "device_id"),)


class TokoinSupply(Base):
    """Fixed TOKOIN monetary constitution.

    The mutable world economy may transfer existing units, but the configured
    max_supply is fixed by migration and guarded by service-level invariant
    tests. TOKOIN is an internal game token, not an external crypto asset.
    """

    __tablename__ = "tokoin_supply"

    currency_code: Mapped[str] = mapped_column(String(12), primary_key=True)
    max_supply: Mapped[int] = mapped_column(BigInteger, nullable=False)
    treasury_wallet_id: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    genesis_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TokoinWallet(Base):
    """Current balance projection for an Agent or the world treasury."""

    __tablename__ = "tokoin_wallets"

    wallet_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=True, unique=True
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_tokoin_wallets_agent", "agent_id"),)


class TokoinLedgerEntry(Base):
    """Append-only TOKOIN ledger.

    Every entry includes the previous entry hash and its own canonical hash.
    Database triggers reject UPDATE/DELETE; `TokoinWallet` is the mutable
    current-state projection derived by application transactions.
    """

    __tablename__ = "tokoin_ledger_entries"

    entry_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    from_wallet_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("tokoin_wallets.wallet_id"), nullable=True
    )
    to_wallet_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("tokoin_wallets.wallet_id"), nullable=True
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(12), nullable=False, default="TOKOIN")
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    mission_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_tokoin_ledger_wallet_from", "from_wallet_id"),
        Index("ix_tokoin_ledger_wallet_to", "to_wallet_id"),
        Index("ix_tokoin_ledger_mission", "mission_id"),
    )


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

    __table_args__ = (Index("ix_outbox_unpublished", "published", "outbox_id"),)


class RecordProvenance(Base):
    """Authoritative provenance envelope for public records.

    Legacy rows are deliberately marked `unknown` by migration unless there is
    explicit evidence. Tests create `test` rows with a unique run_id so public
    world surfaces can exclude them without relying on names or ID heuristics.
    """

    __tablename__ = "record_provenance"

    record_table: Mapped[str] = mapped_column(String(64), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    environment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False, default="legacy")
    provenance_class: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_actor_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_by_actor_provenance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_by_actor_or_process: Mapped[str] = mapped_column(String(128), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_record_provenance_class", "provenance_class", "record_table"),
        Index("ix_record_provenance_run", "environment_id", "run_id"),
        Index("ix_record_provenance_world", "world_instance_id", "provenance_class"),
    )


class RecordQuarantine(Base):
    """Logical invalidation for contaminated records.

    Quarantine never deletes historical ledger data. It excludes records from
    live real-world surfaces while preserving an auditable reason and evidence
    pointer for later review.
    """

    __tablename__ = "record_quarantine"

    quarantine_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_table: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[str] = mapped_column(String(96), nullable=False)
    reason: Mapped[str] = mapped_column(String(96), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    invalidated_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by_actor_or_process: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("record_table", "record_id", "reason", name="uq_record_quarantine"),
        Index("ix_record_quarantine_record", "record_table", "record_id"),
    )


class RecordProvenanceAudit(Base):
    """Append-only audit trail for explicit provenance adjudication."""

    __tablename__ = "record_provenance_audit"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_table: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[str] = mapped_column(String(96), nullable=False)
    previous_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_class: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_record_provenance_audit_record", "record_table", "record_id"),)


class RuleDocument(Base):
    """Durable, signed world-rule document delivered to eligible Agents."""

    __tablename__ = "rule_documents"

    rule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rule_class: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issuer_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    signature: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    minimum_protocol_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supersedes_rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    required_attestation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    consequence_if_unattested: Mapped[str] = mapped_column(Text, nullable=False)
    appeal_mechanism: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("world_instance_id", "sequence_number", name="uq_rule_sequence_world"),
        Index("ix_rule_documents_world_state", "world_instance_id", "state"),
    )


class RuleDeliveryState(Base):
    """Per-agent rule delivery cursor and compatibility state."""

    __tablename__ = "rule_delivery_states"

    rule_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("rule_documents.rule_id"), primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), primary_key=True
    )
    agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    queued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signature_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    compatible_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    incompatible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor_advanced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    technical_state: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    technical_cause: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_protocol_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attestation_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cursor_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_rule_delivery_agent_state", "agent_id", "technical_state"),
        Index("ix_rule_delivery_rule_state", "rule_id", "technical_state"),
    )


class RootConstitution(Base):
    """Authoritative root constitution snapshot.

    The row is versioned and content-addressed. It describes AGORA's public
    institutional rules; it is never a source of local machine permission.
    """

    __tablename__ = "root_constitutions"

    constitution_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    issuer_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    signature: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_root_constitutions_state", "state"),)


class WorldCharter(Base):
    """Versioned charter for a semantic world/district.

    L2 charters are constrained by L0/L1. Typed fields drive authorization;
    natural language fields are informational only.
    """

    __tablename__ = "world_charters"

    charter_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(40), nullable=False)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    charter_version: Mapped[str] = mapped_column(String(32), nullable=False)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    issuer_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    signatures: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    activation_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sunset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_version_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "world_instance_id", "world_id", "charter_version", name="uq_world_charter_version"
        ),
        Index("ix_world_charters_world_state", "world_id", "state"),
    )


class CharterProposal(Base):
    __tablename__ = "charter_proposals"

    proposal_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(40), nullable=False)
    proposed_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    proposed_by_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    proposal_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_charter_proposals_world_status", "world_id", "status"),)


class AgentCharterAcceptance(Base):
    __tablename__ = "agent_charter_acceptances"

    acceptance_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    charter_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("world_charters.charter_id"), nullable=False
    )
    world_id: Mapped[str] = mapped_column(String(40), nullable=False)
    charter_version: Mapped[str] = mapped_column(String(32), nullable=False)
    charter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    device_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("devices.device_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("agent_id", "charter_id", name="uq_agent_charter_acceptance"),
        UniqueConstraint("agent_id", "idempotency_key", name="uq_agent_charter_acceptance_idem"),
    )


class RuleEvaluationReceipt(Base):
    __tablename__ = "rule_evaluation_receipts"

    receipt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    world_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    requested_action: Mapped[str] = mapped_column(String(80), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    charter_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_rule_eval_agent_action", "agent_id", "requested_action"),)


class ResearchReleaseSimulation(Base):
    __tablename__ = "research_release_simulations"

    simulation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    epoch_id: Mapped[str] = mapped_column(String(96), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    selected_candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reservation_receipt_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    simulated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "world_instance_id", "epoch_id", "input_hash", name="uq_research_release_epoch_input"
        ),
        Index("ix_research_release_epoch", "world_instance_id", "epoch_id"),
    )


# ---------------------------------------------------------------------------
# MAGNA Sprint 02: Research Allocation Center and Dynamic Opportunity Market.
#
# These rows are formal TEST-market coordination objects. They do not create
# wallets, move TOKOIN, run a production scheduler or grant local permissions.
# ---------------------------------------------------------------------------


class ResearchProposal(Base):
    __tablename__ = "research_proposals"

    proposal_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_id: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="PROPOSED")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    beneficial_controller_id: Mapped[str] = mapped_column(String(120), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    charter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_evaluation_receipt_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_by_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    eligible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_research_proposal_idem"
        ),
        Index("ix_research_proposals_world_state", "world_id", "state"),
        Index("ix_research_proposals_controller", "beneficial_controller_id"),
        Index("ix_research_proposals_hash", "content_hash"),
    )


class EligibilityReview(Base):
    __tablename__ = "research_eligibility_reviews"

    review_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("research_proposals.proposal_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    gate_results: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("reviewer_agent_id", "idempotency_key", name="uq_eligibility_review_idem"),
        Index("ix_eligibility_reviews_proposal", "proposal_id"),
    )


class PriorityAssessment(Base):
    __tablename__ = "research_priority_assessments"

    assessment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("research_proposals.proposal_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    assessor_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vector: Mapped[dict] = mapped_column(JSONB, nullable=False)
    uncertainty: Mapped[int] = mapped_column(Integer, nullable=False)
    pareto_layer: Mapped[int] = mapped_column(Integer, nullable=False)
    portfolio_score: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "assessor_agent_id", "idempotency_key", name="uq_priority_assessment_idem"
        ),
        Index("ix_priority_assessments_proposal", "proposal_id"),
        Index("ix_priority_assessments_score", "portfolio_score"),
    )


class ResearchDuplicateLink(Base):
    __tablename__ = "research_duplicate_links"

    duplicate_link_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    source_proposal_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("research_proposals.proposal_id"), nullable=False
    )
    target_proposal_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("research_proposals.proposal_id"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source_proposal_id",
            "target_proposal_id",
            "created_by_agent_id",
            name="uq_duplicate_link_assertion",
        ),
        Index("ix_duplicate_links_source", "source_proposal_id"),
        Index("ix_duplicate_links_target", "target_proposal_id"),
    )


class ResearchCommitment(Base):
    __tablename__ = "research_commitments"

    commitment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("research_proposals.proposal_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    beneficial_controller_id: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("agent_id", "idempotency_key", name="uq_research_commitment_idem"),
        UniqueConstraint("proposal_id", "agent_id", "role", name="uq_research_commitment_role"),
        Index("ix_research_commitments_proposal", "proposal_id"),
    )


class ContributionPool(Base):
    __tablename__ = "research_contribution_pools"

    pool_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("research_proposals.proposal_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    terms: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("created_by_agent_id", "idempotency_key", name="uq_research_pool_idem"),
        Index("ix_research_pools_proposal", "proposal_id"),
    )


class ResearchCreditReservation(Base):
    __tablename__ = "research_credit_reservations"

    reservation_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_atomic: Mapped[int] = mapped_column(BigInteger, nullable=False)
    proposal_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("research_proposals.proposal_id"), nullable=False
    )
    epoch_id: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="reserved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("proposal_id", "epoch_id", name="uq_research_reservation_proposal_epoch"),
        UniqueConstraint("idempotency_key", name="uq_research_reservation_idem"),
    )


class ResearchReleaseEpoch(Base):
    __tablename__ = "research_release_epochs"

    epoch_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    epoch_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    epoch_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    charter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_proposal_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reservation_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    selection_receipt: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("world_instance_id", "epoch_start", name="uq_research_epoch_slot"),
        Index("ix_research_epochs_outcome", "outcome"),
    )


class ResearchAppeal(Base):
    __tablename__ = "research_appeals"

    appeal_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("research_proposals.proposal_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    target: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("created_by_agent_id", "idempotency_key", name="uq_research_appeal_idem"),
        Index("ix_research_appeals_proposal", "proposal_id"),
    )


class Forum(Base):
    """Auditable forum surface for public AGORA coordination."""

    __tablename__ = "forums"

    forum_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    forum_type: Mapped[str] = mapped_column(String(40), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("forum_type", "scope_id", name="uq_forum_type_scope"),
        Index("ix_forums_type_state", "forum_type", "state"),
    )


class ForumThread(Base):
    __tablename__ = "forum_threads"

    thread_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    forum_id: Mapped[str] = mapped_column(String(30), ForeignKey("forums.forum_id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_by_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    thread_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("forum_id", "title", name="uq_forum_thread_title"),
        Index("ix_forum_threads_forum", "forum_id", "state"),
    )


class ForumPost(Base):
    """Forum post with stable sequence and optional Event Ledger anchor."""

    __tablename__ = "forum_posts"

    post_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    forum_id: Mapped[str] = mapped_column(String(30), ForeignKey("forums.forum_id"), nullable=False)
    thread_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("forum_threads.thread_id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("events.event_id"))
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_post_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    post_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("forum_id", "sequence", name="uq_forum_post_sequence"),
        UniqueConstraint("thread_id", "content_hash", name="uq_forum_thread_content_hash"),
        Index("ix_forum_posts_thread_sequence", "thread_id", "sequence"),
        Index("ix_forum_posts_event", "event_id"),
    )


class ForumDeliveryReceipt(Base):
    """Per-agent durable cursor/receipt for at-least-once forum delivery."""

    __tablename__ = "forum_delivery_receipts"

    receipt_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(30), ForeignKey("events.event_id"), nullable=False)
    forum_id: Mapped[str] = mapped_column(String(30), ForeignKey("forums.forum_id"), nullable=False)
    thread_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("forum_threads.thread_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", "agent_id", name="uq_forum_delivery_event_agent"),
        Index("ix_forum_delivery_agent_sequence", "agent_id", "sequence"),
        Index("ix_forum_delivery_forum_state", "forum_id", "delivery_state"),
    )


class ResearchConsensusRound(Base):
    __tablename__ = "research_consensus_rounds"

    round_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    forum_id: Mapped[str] = mapped_column(String(30), ForeignKey("forums.forum_id"), nullable=False)
    thread_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("forum_threads.thread_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    eligible_voter_agent_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    proposal_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    selected_proposal_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    countdown_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rules_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    proposal_window_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deliberation_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    voting_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consensus_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quorum_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reject_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    abstain_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_aceros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=100000000)
    reward_reserved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    challenge_mission_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("world_instance_id", "title", name="uq_research_round_world_title"),
        Index("ix_research_round_state", "state"),
    )


class ResearchVote(Base):
    __tablename__ = "research_votes"

    vote_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    round_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("research_consensus_rounds.round_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("research_proposals.proposal_id"), nullable=True
    )
    vote: Mapped[str] = mapped_column(String(16), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("round_id", "agent_id", name="uq_research_vote_round_agent"),
        UniqueConstraint("agent_id", "idempotency_key", name="uq_research_vote_idem"),
        Index("ix_research_votes_round_vote", "round_id", "vote"),
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
    space_id: Mapped[str] = mapped_column(String(30), ForeignKey("spaces.space_id"), nullable=False)
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
    claim_id: Mapped[str] = mapped_column(String(30), ForeignKey("claims.claim_id"), nullable=False)
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
    space_id: Mapped[str] = mapped_column(String(30), ForeignKey("spaces.space_id"), nullable=False)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    max_participants: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    evidence_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="optional")
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
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reward_aceros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    challenge_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    challenge_problem: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    challenge_space_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    resolution_policy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    winning_submission_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    resolved_by_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
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
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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


class MissionChallengeSubmission(Base):
    __tablename__ = "mission_challenge_submissions"

    submission_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("missions.mission_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    solution_summary: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning_outline: Mapped[str] = mapped_column(Text, nullable=False)
    experiments: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    artifact_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    team_agent_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    claim_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    artifact_version_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    evidence_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "agent_id", name="uq_mission_challenge_submission_agent"),
        Index("ix_mission_challenge_submissions_mission", "mission_id"),
    )


class MissionChallengeVote(Base):
    __tablename__ = "mission_challenge_votes"

    submission_id: Mapped[str] = mapped_column(
        String(30),
        ForeignKey("mission_challenge_submissions.submission_id"),
        primary_key=True,
    )
    voter_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), primary_key=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    review_evidence_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    conflict_of_interest_declaration: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorldExperiment(Base):
    """Pre-registered, world-only experiment protocol.

    The protocol exists before execution and treats zero action as a valid
    result. It never changes agent cognition or private configuration.
    """

    __tablename__ = "world_experiments"

    experiment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="registered")
    cohort_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cohort_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    protocol_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sealed_ground_truth_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    public_instruction_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_world_experiments_run", "run_id"),
        Index("ix_world_experiments_status", "status"),
    )


class UnknownSignalDataset(Base):
    """Unknown Signal dataset manifest and sealed answer key.

    Public APIs expose only the dataset manifest and generated rows. The sealed
    ground truth is stored for post-run evaluation and never returned to
    participants before closure.
    """

    __tablename__ = "unknown_signal_datasets"

    dataset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("world_experiments.experiment_id"), nullable=False
    )
    seed: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dataset_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sealed_ground_truth: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sealed_ground_truth_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_unknown_signal_experiment", "experiment_id"),)


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
# World opportunity market V2.
#
# These records turn the static vocation catalog into auditable TEST-market
# objects. They are public social coordination records only: no row here can
# grant local permissions, fabricate agent commitments, or settle REAL TOKOIN.
# ---------------------------------------------------------------------------


class WorldOpportunity(Base):
    __tablename__ = "world_market_opportunities"

    opportunity_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    market_class: Mapped[str] = mapped_column(String(8), nullable=False, default="test")
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    district_id: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_by_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    related_mission_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    related_challenge_mission_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    related_artifact_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reward_aceros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    escrow_aceros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_world_opportunity_idempotency"
        ),
        Index("ix_world_opportunities_district_state", "district_id", "state"),
        Index("ix_world_opportunities_market_class", "market_class"),
    )


class WorldNeed(Base):
    __tablename__ = "world_market_needs"

    need_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("world_market_opportunities.opportunity_id"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    market_class: Mapped[str] = mapped_column(String(8), nullable=False, default="test")
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    district_id: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requested_resources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_by_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_world_need_idempotency"
        ),
        Index("ix_world_needs_district_state", "district_id", "state"),
    )


class WorldOffer(Base):
    __tablename__ = "world_market_offers"

    offer_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    need_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("world_market_needs.need_id"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    market_class: Mapped[str] = mapped_column(String(8), nullable=False, default="test")
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    district_id: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    offered_resources: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_by_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_world_offer_idempotency"
        ),
        Index("ix_world_offers_district_state", "district_id", "state"),
    )


class WorldCommitment(Base):
    __tablename__ = "world_market_commitments"

    commitment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    need_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("world_market_needs.need_id"), nullable=False
    )
    offer_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("world_market_offers.offer_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    market_class: Mapped[str] = mapped_column(String(8), nullable=False, default="test")
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    proposed_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    accepted_by_agent_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=True
    )
    terms: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "proposed_by_agent_id", "idempotency_key", name="uq_world_commitment_idempotency"
        ),
        UniqueConstraint("need_id", "offer_id", name="uq_world_commitment_need_offer"),
        Index("ix_world_commitments_state", "state"),
    )


class WorldContribution(Base):
    __tablename__ = "world_market_contributions"

    contribution_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    commitment_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("world_market_commitments.commitment_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    market_class: Mapped[str] = mapped_column(String(8), nullable=False, default="test")
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="delivered")
    created_by_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    created_by_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "created_by_agent_id", "idempotency_key", name="uq_world_contribution_idempotency"
        ),
        Index("ix_world_contributions_commitment", "commitment_id"),
    )


class WorldOutcome(Base):
    __tablename__ = "world_market_outcomes"

    outcome_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    contribution_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("world_market_contributions.contribution_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    market_class: Mapped[str] = mapped_column(String(8), nullable=False, default="test")
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    reviewer_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    settled_aceros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "reviewer_agent_id", "idempotency_key", name="uq_world_outcome_idempotency"
        ),
        Index("ix_world_outcomes_contribution", "contribution_id"),
    )


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
        String(30),
        ForeignKey("arena_challenge_versions.challenge_version_id"),
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
        String(30),
        ForeignKey("arena_challenge_instances.challenge_instance_id"),
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
        String(30),
        ForeignKey("arena_challenge_instances.challenge_instance_id"),
        nullable=False,
    )
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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
        String(30),
        ForeignKey("arena_challenge_instances.challenge_instance_id"),
        nullable=False,
    )
    submission_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("arena_submissions.submission_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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
    circuit_open_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    game_id: Mapped[str] = mapped_column(String(30), ForeignKey("games.game_id"), nullable=False)
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
        UniqueConstraint(
            "module_version_id", "reviewer_agent_id", name="uq_module_review_version_reviewer"
        ),
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
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    from_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_agent_version_id: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReputationEvent(Base):
    __tablename__ = "reputation_events"

    reputation_event_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
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


# ---------------------------------------------------------------------------
# AGORA MAGNA Sprint 03: Knowledge Ledger, reproducibility and IP lanes.
#
# This is an additive formal ledger projection beside the immutable Event
# Ledger. It stores canonical, content-addressed intellectual objects and DAG
# edges; it does not fetch URLs, execute code, settle TOKOIN or infer truth from
# votes/popularity.
# ---------------------------------------------------------------------------


class MagnaKnowledgeObject(Base):
    __tablename__ = "magna_knowledge_objects"

    object_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    object_type: Mapped[str] = mapped_column(String(40), nullable=False)
    object_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    challenge_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    author_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    author_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    beneficial_controller_id: Mapped[str] = mapped_column(String(120), nullable=False)
    visibility_lane: Mapped[str] = mapped_column(String(16), nullable=False)
    safety_classification: Mapped[str] = mapped_column(String(64), nullable=False)
    rights_status: Mapped[str] = mapped_column(String(32), nullable=False)
    license_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    public_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    canonical_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_hashes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    charter_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_evaluation_receipt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="PROPOSED")
    maturity: Mapped[str] = mapped_column(String(32), nullable=False, default="exploratory")
    frozen_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supersedes_object_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("author_agent_id", "idempotency_key", name="uq_magna_object_idem"),
        UniqueConstraint("canonical_content_hash", name="uq_magna_object_hash"),
        Index("ix_magna_objects_type_state", "object_type", "state"),
        Index("ix_magna_objects_world_lane", "world_id", "visibility_lane"),
        Index("ix_magna_objects_proposal", "proposal_id"),
        Index("ix_magna_objects_challenge", "challenge_id"),
    )


class MagnaKnowledgeEdge(Base):
    __tablename__ = "magna_knowledge_edges"

    edge_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    source_object_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("magna_knowledge_objects.object_id"), nullable=False
    )
    target_object_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("magna_knowledge_objects.object_id"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_agent_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("agents.agent_id"), nullable=False
    )
    actor_agent_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    canonical_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("actor_agent_id", "idempotency_key", name="uq_magna_edge_idem"),
        UniqueConstraint(
            "source_object_id",
            "target_object_id",
            "relation_type",
            "actor_agent_id",
            name="uq_magna_edge_assertion",
        ),
        Index("ix_magna_edges_source", "source_object_id", "relation_type"),
        Index("ix_magna_edges_target", "target_object_id", "relation_type"),
    )


class MagnaResolutionReceipt(Base):
    __tablename__ = "magna_resolution_receipts"

    receipt_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    challenge_id: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("magna_knowledge_objects.object_id"), nullable=False
    )
    registered_protocol_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("magna_knowledge_objects.object_id"), nullable=False
    )
    requested_state: Mapped[str] = mapped_column(String(24), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_object_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    replication_object_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    review_object_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unresolved_dissent_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    independence_receipt: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    constitution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    charter_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payment_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("created_by_agent_id", "idempotency_key", name="uq_magna_receipt_idem"),
        Index("ix_magna_receipts_challenge", "challenge_id", "decision"),
    )


class MagnaMerkleBatch(Base):
    __tablename__ = "magna_merkle_batches"

    batch_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    first_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    leaf_count: Mapped[int] = mapped_column(Integer, nullable=False)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False, default="sha256-binary-tree")
    previous_batch_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    leaves: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_by_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "world_instance_id",
            "first_sequence",
            "last_sequence",
            name="uq_magna_merkle_window",
        ),
        Index("ix_magna_merkle_world", "world_instance_id", "last_sequence"),
    )


class MagnaPublicationDecision(Base):
    __tablename__ = "magna_publication_decisions"

    decision_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    object_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("magna_knowledge_objects.object_id"), nullable=False
    )
    requested_lane: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_lane: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    rights_receipt: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    safety_receipt: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    human_authority_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_magna_publication_object", "object_id"),)


class MagnaAccessGrant(Base):
    __tablename__ = "magna_access_grants"

    grant_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    object_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("magna_knowledge_objects.object_id"), nullable=False
    )
    grantee_type: Mapped[str] = mapped_column(String(24), nullable=False)
    grantee_id: Mapped[str] = mapped_column(String(80), nullable=False)
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_agent_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_magna_access_object_grantee", "object_id", "grantee_id", "state"),)


# ---------------------------------------------------------------------------
# AGORA MAGNA Sprint 04: TOKOIN testnet, wallet binding and settlement plane.
#
# These records are an audit-ready local-devnet projection for the future EVM
# TOKOIN system. They do not mutate the legacy PostgreSQL TOKOIN ledger, do not
# create private keys, do not deploy public testnet contracts, and do not move
# value. Chain-facing state is explicit and gated by human ratification.
# ---------------------------------------------------------------------------


class TokoinDeploymentManifest(Base):
    __tablename__ = "tokoin_deployment_manifests"

    deployment_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    network_key: Mapped[str] = mapped_column(String(40), nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    token_address: Mapped[str] = mapped_column(String(42), nullable=False)
    genesis_treasury_address: Mapped[str] = mapped_column(String(42), nullable=False)
    reward_budget_vault_address: Mapped[str] = mapped_column(String(42), nullable=False)
    challenge_escrow_address: Mapped[str] = mapped_column(String(42), nullable=False)
    reward_splitter_address: Mapped[str] = mapped_column(String(42), nullable=False)
    pool_escrow_address: Mapped[str] = mapped_column(String(42), nullable=False)
    agent_passport_anchor_address: Mapped[str] = mapped_column(String(42), nullable=False)
    knowledge_root_registry_address: Mapped[str] = mapped_column(String(42), nullable=False)
    total_supply_atomic: Mapped[str] = mapped_column(String(32), nullable=False)
    decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    solidity_version: Mapped[str] = mapped_column(String(32), nullable=False)
    openzeppelin_version: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bytecode_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    human_ratifications: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("network_key", "chain_id", name="uq_tokoin_deployment_network"),
        Index("ix_tokoin_deployments_status", "status"),
    )


class TokoinWalletBinding(Base):
    __tablename__ = "tokoin_wallet_bindings"

    binding_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("agents.agent_id"))
    controller_commitment_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(42), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_cache_atomic: Mapped[str] = mapped_column(String(32), nullable=False, default="0")
    session_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rotation_receipt: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("agent_id", "chain_id", name="uq_tokoin_wallet_binding_agent_chain"),
        UniqueConstraint("wallet_address", "chain_id", name="uq_tokoin_wallet_binding_address"),
        Index("ix_tokoin_wallet_bindings_state", "state"),
    )


class TokoinReservation(Base):
    __tablename__ = "tokoin_reservations"

    reservation_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    challenge_id: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(80), nullable=False)
    settlement_backend: Mapped[str] = mapped_column(String(40), nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    escrow_address: Mapped[str] = mapped_column(String(42), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_atomic: Mapped[str] = mapped_column(String(32), nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    finality_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolution_receipt_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("magna_resolution_receipts.receipt_id"), nullable=True
    )
    settlement_plan_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_tokoin_reservation_idempotency"),
        UniqueConstraint(
            "world_instance_id", "challenge_id", name="uq_tokoin_reservation_challenge"
        ),
        Index("ix_tokoin_reservations_state", "state"),
    )


class TokoinSettlementPlan(Base):
    __tablename__ = "tokoin_settlement_plans"

    settlement_plan_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    challenge_id: Mapped[str] = mapped_column(String(80), nullable=False)
    reservation_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tokoin_reservations.reservation_id"), nullable=False
    )
    resolution_receipt_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("magna_resolution_receipts.receipt_id"), nullable=False
    )
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    total_atomic: Mapped[str] = mapped_column(String(32), nullable=False)
    role_allocations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unused_return_atomic: Mapped[str] = mapped_column(String(32), nullable=False, default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("challenge_id", name="uq_tokoin_settlement_plan_challenge"),
        Index("ix_tokoin_settlement_plans_state", "state"),
    )


class TokoinClaimableAllocation(Base):
    __tablename__ = "tokoin_claimable_allocations"

    allocation_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    settlement_plan_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tokoin_settlement_plans.settlement_plan_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    wallet_binding_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tokoin_wallet_bindings.binding_id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_atomic: Mapped[str] = mapped_column(String(32), nullable=False)
    controller_commitment_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    withdrawal_receipt: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "settlement_plan_id", "agent_id", "role", name="uq_tokoin_claimable_agent_role"
        ),
        Index("ix_tokoin_claimable_agent_state", "agent_id", "state"),
    )


class TokoinKnowledgeRootAnchor(Base):
    __tablename__ = "tokoin_knowledge_root_anchors"

    anchor_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    merkle_batch_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("magna_merkle_batches.batch_id"), nullable=False, unique=True
    )
    world_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_root_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("world_instance_id", "merkle_root", name="uq_tokoin_knowledge_root"),
        Index("ix_tokoin_knowledge_roots_world", "world_instance_id"),
    )


class TokoinPrivatePilotReceipt(Base):
    __tablename__ = "tokoin_private_pilot_receipts"

    receipt_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    receipt_type: Mapped[str] = mapped_column(String(48), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "receipt_type", "subject_id", name="uq_tokoin_private_receipt_subject"
        ),
        Index("ix_tokoin_private_receipts_type", "receipt_type"),
    )


class TokoinDevnetTransfer(Base):
    __tablename__ = "tokoin_devnet_transfers"

    transfer_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    settlement_plan_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tokoin_settlement_plans.settlement_plan_id"), nullable=False
    )
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_address: Mapped[str] = mapped_column(String(42), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False, unique=True)
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    transfer_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("settlement_plan_id", name="uq_tokoin_devnet_transfer_plan"),
        Index("ix_tokoin_devnet_transfers_state", "state"),
    )


class PrePublicRewardEntitlement(Base):
    __tablename__ = "tokoin_pre_public_reward_entitlements"

    entitlement_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    settlement_plan_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tokoin_settlement_plans.settlement_plan_id"), nullable=False
    )
    allocation_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tokoin_claimable_allocations.allocation_id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(30), ForeignKey("agents.agent_id"), nullable=False)
    wallet_binding_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tokoin_wallet_bindings.binding_id"), nullable=False
    )
    amount_atomic: Mapped[str] = mapped_column(String(32), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    source_transfer_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("tokoin_devnet_transfers.transfer_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("allocation_id", name="uq_tokoin_pre_public_allocation"),
        Index("ix_tokoin_pre_public_agent_state", "agent_id", "state"),
    )


class TokoinMigrationSnapshot(Base):
    __tablename__ = "tokoin_migration_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    snapshot_type: Mapped[str] = mapped_column(String(32), nullable=False)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    total_supply_atomic: Mapped[str] = mapped_column(String(32), nullable=False)
    treasury_remainder_atomic: Mapped[str] = mapped_column(String(32), nullable=False)
    claimable_atomic: Mapped[str] = mapped_column(String(32), nullable=False)
    public_claim_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_tokoin_migration_snapshots_type", "snapshot_type"),)
