"""Agent lineage and cryptographic passports.

Post-roadmap Sprint 1 keeps identity at the edge while giving AGORA a durable
public continuity model:
- genesis is one canonical birth per Agent ID;
- device continuity is separate from agent authentication;
- PassportSession is short-lived, signed, replay-bound and revocation-aware;
- no raw hardware identifiers are accepted or stored.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.config import get_settings
from agora_api.crypto import b64url_encode, verify_signature
from agora_api.errors import AuthRequired, ChallengeInvalid, Conflict, DeviceRevoked
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_challenge_id,
    new_device_installation_key_id,
    new_key_rotation_id,
    new_passport_id,
)
from agora_api.models import (
    Agent,
    AgentDeviceAuthorization,
    AgentGenesis,
    AgentKeyRotation,
    Device,
    DeviceInstallationKey,
    EnrollmentChallenge,
    Event,
    PassportSession,
)

DEFAULT_SCOPES = [
    "world.enter",
    "world.speak",
    "world.observe",
    "a2a.relay",
    "mcp.local",
]
CONSTITUTION_HASH = hashlib.sha256(
    b"AGORA Constitution: edge intelligence, untrusted remote content, consensus is not truth"
).hexdigest()
ENROLL_CONTEXT = "agora.enrollment.v1"
PASSPORT_CONTEXT = "agora.passport.issue.v1"
ROTATE_CONTEXT = "agora.agent_key.rotate.v1"
MAX_CLOCK_SKEW = timedelta(seconds=300)


class PassportRejected(AuthRequired):
    code = "passport_rejected"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_passport(payload: dict[str, Any]) -> str:
    settings = get_settings()
    if settings.is_production and settings.passport_signing_secret.endswith("change-me"):
        raise AuthRequired("Production passport signing secret is not configured.")
    raw = canonical_json(payload).encode()
    signature = hmac.new(
        settings.passport_signing_secret.encode(),
        raw,
        hashlib.sha256,
    ).digest()
    return (
        b64url_encode(raw)
        + "."
        + b64url_encode(signature)
    )


def verify_passport_token(token: str) -> dict[str, Any]:
    try:
        raw_b64, sig_b64 = token.split(".", 1)
        raw = _b64url_decode(raw_b64)
        expected = hmac.new(
            get_settings().passport_signing_secret.encode(),
            raw,
            hashlib.sha256,
        ).digest()
        actual = _b64url_decode(sig_b64)
    except Exception as exc:  # noqa: BLE001 - invalid token shape
        raise PassportRejected("Passport is malformed.") from exc
    if not hmac.compare_digest(actual, expected):
        raise PassportRejected("Passport signature is invalid.")
    payload = json.loads(raw.decode())
    expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    if expires_at <= now_utc():
        raise PassportRejected("Passport expired.")
    return payload


def _b64url_decode(value: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def enrollment_message(
    challenge_id: str,
    nonce: str,
    agent_id: str,
    device_id: str,
    constitution_hash: str,
) -> bytes:
    return (
        f"{ENROLL_CONTEXT}|{challenge_id}|{nonce}|{agent_id}|{device_id}|"
        f"{constitution_hash}"
    ).encode()


def passport_issue_message(agent_id: str, device_id: str, timestamp: str) -> bytes:
    return f"{PASSPORT_CONTEXT}|{agent_id}|{device_id}|{timestamp}".encode()


def rotation_message(agent_id: str, old_key: str, new_key: str, timestamp: str) -> bytes:
    return f"{ROTATE_CONTEXT}|{agent_id}|{old_key}|{new_key}|{timestamp}".encode()


async def ensure_genesis(
    session: AsyncSession,
    *,
    agent: Agent,
    device: Device,
    trace_id: str | None = None,
) -> AgentGenesis:
    existing = await session.get(AgentGenesis, agent.agent_id)
    if existing is not None:
        return existing
    event = await append_event(
        session,
        event_type="agent.genesis",
        actor={"agent_id": agent.agent_id, "device_id": device.device_id},
        payload={
            "agent_id": agent.agent_id,
            "first_device_id": device.device_id,
            "agent_public_key": device.public_key,
            "device_public_key": device.public_key,
            "constitution_hash": CONSTITUTION_HASH,
            "hardware_identifier_collected": False,
        },
        trace_id=trace_id,
    )
    await session.flush()
    genesis = AgentGenesis(
        agent_id=agent.agent_id,
        genesis_event_id=event.event_id,
        first_device_id=device.device_id,
        agent_public_key=device.public_key,
        device_public_key=device.public_key,
        constitution_hash=CONSTITUTION_HASH,
        born_at=event.occurred_at,
    )
    session.add(genesis)
    await session.flush()
    return genesis


async def ensure_authorization(
    session: AsyncSession,
    *,
    agent_id: str,
    device_id: str,
    assurance_level: str = "device",
    authorized_by_device_id: str | None = None,
) -> AgentDeviceAuthorization:
    existing = await session.get(AgentDeviceAuthorization, (agent_id, device_id))
    if existing is not None:
        return existing
    auth = AgentDeviceAuthorization(
        agent_id=agent_id,
        device_id=device_id,
        status="authorized",
        assurance_level=assurance_level,
        authorized_by_device_id=authorized_by_device_id,
        authorized_at=now_utc(),
        revoked_at=None,
    )
    session.add(auth)
    await session.flush()
    return auth


async def create_enrollment_challenge(session: AsyncSession, payload: dict[str, Any]) -> dict:
    validate_boundary("passports.schema.json", "/$defs/EnrollmentChallengeRequest", payload)
    device = await session.get(Device, payload["device_id"])
    agent = await session.get(Agent, payload["agent_id"])
    if agent is None or device is None or device.agent_id != agent.agent_id:
        raise ChallengeInvalid("Agent/device enrollment target is invalid.")
    if device.status == "revoked":
        raise DeviceRevoked("Device has been revoked.")
    challenge = EnrollmentChallenge(
        challenge_id=new_challenge_id(),
        agent_id=agent.agent_id,
        device_id=device.device_id,
        nonce=b64url_encode(secrets.token_bytes(32)),
        constitution_hash=payload.get("constitution_hash") or CONSTITUTION_HASH,
        expires_at=now_utc() + timedelta(seconds=get_settings().challenge_ttl_seconds),
        consumed_at=None,
        created_at=now_utc(),
    )
    session.add(challenge)
    await session.commit()
    return {
        "challenge_id": challenge.challenge_id,
        "nonce": challenge.nonce,
        "constitution_hash": challenge.constitution_hash,
        "expires_at": challenge.expires_at.isoformat().replace("+00:00", "Z"),
    }


async def attest_enrollment(
    session: AsyncSession, payload: dict[str, Any], trace_id: str | None
) -> dict:
    validate_boundary("passports.schema.json", "/$defs/EnrollmentAttestRequest", payload)
    challenge = await session.get(EnrollmentChallenge, payload["challenge_id"])
    if challenge is None:
        raise ChallengeInvalid("Unknown enrollment challenge.")
    if challenge.expires_at <= now_utc():
        raise ChallengeInvalid("Enrollment challenge expired.")
    if challenge.agent_id != payload["agent_id"] or challenge.device_id != payload["device_id"]:
        raise ChallengeInvalid("Challenge target mismatch.")

    result = await session.execute(
        update(EnrollmentChallenge)
        .where(
            EnrollmentChallenge.challenge_id == challenge.challenge_id,
            EnrollmentChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=now_utc())
    )
    if getattr(result, "rowcount", 0) != 1:
        raise ChallengeInvalid("Enrollment challenge already used.")

    device = await session.get(Device, challenge.device_id)
    agent = await session.get(Agent, challenge.agent_id)
    if agent is None or device is None or device.agent_id != agent.agent_id:
        raise ChallengeInvalid("Agent/device target is invalid.")
    if device.status == "revoked":
        raise DeviceRevoked("Device has been revoked.")
    message = enrollment_message(
        challenge.challenge_id,
        challenge.nonce,
        challenge.agent_id,
        challenge.device_id,
        challenge.constitution_hash,
    )
    if not verify_signature(device.public_key, message, payload["device_signature"]):
        raise ChallengeInvalid("Device enrollment signature failed.")
    # Current Sprint keeps initial agent lineage key equal to the device key.
    # Rotation path below allows future separation without changing Agent ID.
    if not verify_signature(device.public_key, message, payload["agent_signature"]):
        raise ChallengeInvalid("Agent enrollment signature failed.")

    genesis = await ensure_genesis(session, agent=agent, device=device, trace_id=trace_id)
    authorization = await ensure_authorization(
        session,
        agent_id=agent.agent_id,
        device_id=device.device_id,
        assurance_level="device",
    )
    await append_event(
        session,
        event_type="agent.enrollment_attested",
        actor={"agent_id": agent.agent_id, "device_id": device.device_id},
        payload={
            "agent_id": agent.agent_id,
            "device_id": device.device_id,
            "classification": "KNOWN_AGENT_KNOWN_DEVICE",
            "constitution_hash": challenge.constitution_hash,
        },
        trace_id=trace_id,
    )
    await session.commit()
    return {
        "agent_id": agent.agent_id,
        "device_id": device.device_id,
        "classification": classify_continuity(agent, device, authorization),
        "genesis_event_id": genesis.genesis_event_id,
        "constitution_hash": genesis.constitution_hash,
    }


def classify_continuity(
    agent: Agent | None,
    device: Device | None,
    authorization: AgentDeviceAuthorization | None,
) -> str:
    if (
        agent is not None
        and device is not None
        and authorization
        and authorization.status == "authorized"
    ):
        return "KNOWN_AGENT_KNOWN_DEVICE"
    if agent is not None and device is not None:
        return "KNOWN_AGENT_UNAUTHORIZED_DEVICE"
    if agent is None and device is not None:
        return "NEW_AGENT_KNOWN_DEVICE"
    return "NEW_AGENT_NEW_DEVICE"


async def issue_passport(
    session: AsyncSession, payload: dict[str, Any], trace_id: str | None
) -> dict:
    validate_boundary("passports.schema.json", "/$defs/PassportIssueRequest", payload)
    agent = await session.get(Agent, payload["agent_id"])
    device = await session.get(Device, payload["device_id"])
    authorization = await session.get(
        AgentDeviceAuthorization, (payload["agent_id"], payload["device_id"])
    )
    if agent is None or device is None or device.agent_id != payload["agent_id"]:
        raise AuthRequired("Unknown agent/device for passport.")
    if device.status == "revoked":
        raise DeviceRevoked("Device has been revoked.")
    if authorization is None or authorization.status != "authorized":
        raise AuthRequired("Device is not authorized for ordinary passport issuance.")
    try:
        ts = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthRequired("Invalid passport timestamp.") from exc
    if abs(datetime.now(UTC) - ts) > MAX_CLOCK_SKEW:
        raise AuthRequired("Passport timestamp outside acceptance window.")
    if not verify_signature(
        device.public_key,
        passport_issue_message(agent.agent_id, device.device_id, payload["timestamp"]),
        payload["signature"],
    ):
        raise AuthRequired("Passport signature verification failed.")

    genesis = await ensure_genesis(session, agent=agent, device=device, trace_id=trace_id)
    nonce = secrets.token_urlsafe(24)
    issued_at = now_utc()
    expires_at = issued_at + timedelta(seconds=get_settings().passport_ttl_seconds)
    scopes = payload.get("scopes") or DEFAULT_SCOPES
    passport_payload = {
        "passport_id": new_passport_id(),
        "agent_id": agent.agent_id,
        "agent_version_id": agent.current_version_id,
        "device_id": device.device_id,
        "constitution_hash": genesis.constitution_hash,
        "scopes": scopes,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "nonce": nonce,
        "assurance_level": authorization.assurance_level,
    }
    passport_token = sign_passport(passport_payload)
    session.add(
        PassportSession(
            passport_id=passport_payload["passport_id"],
            agent_id=agent.agent_id,
            device_id=device.device_id,
            token_hash=_sha(passport_token),
            nonce_hash=_sha(nonce),
            constitution_hash=genesis.constitution_hash,
            scopes=scopes,
            assurance_level=authorization.assurance_level,
            issued_at=issued_at,
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    await append_event(
        session,
        event_type="passport.issued",
        actor={"agent_id": agent.agent_id, "device_id": device.device_id},
        payload={
            "passport_id": passport_payload["passport_id"],
            "agent_id": agent.agent_id,
            "device_id": device.device_id,
            "scopes": scopes,
            "constitution_hash": genesis.constitution_hash,
            "expires_at": passport_payload["expires_at"],
        },
        trace_id=trace_id,
    )
    await session.commit()
    return {"passport": passport_payload, "passport_token": passport_token}


async def verify_passport(session: AsyncSession, token: str) -> PassportSession:
    payload = verify_passport_token(token)
    row = (
        await session.execute(
            select(PassportSession).where(PassportSession.token_hash == _sha(token))
        )
    ).scalar_one_or_none()
    if row is None:
        raise PassportRejected("Passport was not issued by this AGORA.")
    if row.revoked_at is not None or row.expires_at <= now_utc():
        raise PassportRejected("Passport is no longer active.")
    if payload["passport_id"] != row.passport_id:
        raise PassportRejected("Passport identity mismatch.")
    device = await session.get(Device, row.device_id)
    if device is None or device.status == "revoked":
        raise DeviceRevoked("Device has been revoked.")
    return row


async def authorize_device(
    session: AsyncSession,
    *,
    agent_id: str,
    target_device_id: str,
    current_device: Device,
    trace_id: str | None,
    assurance_level: str = "device",
) -> dict:
    if current_device.agent_id != agent_id:
        raise AuthRequired("Current device cannot authorize devices for another agent.")
    target = await session.get(Device, target_device_id)
    if target is None or target.agent_id != agent_id:
        raise AuthRequired("Target device does not belong to this agent.")
    if current_device.status == "revoked" or target.status == "revoked":
        raise DeviceRevoked("Device has been revoked.")
    auth = await ensure_authorization(
        session,
        agent_id=agent_id,
        device_id=target_device_id,
        assurance_level=assurance_level,
        authorized_by_device_id=current_device.device_id,
    )
    if auth.status != "authorized":
        auth.status = "authorized"
        auth.assurance_level = assurance_level
        auth.authorized_by_device_id = current_device.device_id
        auth.authorized_at = now_utc()
        auth.revoked_at = None
    await append_event(
        session,
        event_type="agent.device_authorized",
        actor={"agent_id": agent_id, "device_id": current_device.device_id},
        payload={"agent_id": agent_id, "device_id": target_device_id},
        trace_id=trace_id,
    )
    await session.commit()
    return {"agent_id": agent_id, "device_id": target_device_id, "status": auth.status}


async def rotate_agent_key(
    session: AsyncSession,
    *,
    agent_id: str,
    current_device: Device,
    payload: dict[str, Any],
    trace_id: str | None,
) -> dict:
    validate_boundary("passports.schema.json", "/$defs/RotateAgentKeyRequest", payload)
    genesis = await session.get(AgentGenesis, agent_id)
    if genesis is None:
        agent = await session.get(Agent, agent_id)
        if agent is None or current_device.agent_id != agent_id:
            raise AuthRequired("Unknown agent for key rotation.")
        genesis = await ensure_genesis(
            session, agent=agent, device=current_device, trace_id=trace_id
        )
    if current_device.agent_id != agent_id or current_device.status == "revoked":
        raise AuthRequired("Current device cannot rotate this agent key.")
    message = rotation_message(
        agent_id,
        genesis.agent_public_key,
        payload["new_public_key"],
        payload["timestamp"],
    )
    if not verify_signature(genesis.agent_public_key, message, payload["old_key_signature"]):
        raise AuthRequired("Old agent key signature failed.")
    if not verify_signature(payload["new_public_key"], message, payload["new_key_signature"]):
        raise AuthRequired("New agent key signature failed.")
    rotation = AgentKeyRotation(
        rotation_id=new_key_rotation_id(),
        agent_id=agent_id,
        device_id=current_device.device_id,
        old_public_key=genesis.agent_public_key,
        new_public_key=payload["new_public_key"],
        rotation_event_id=None,
        created_at=now_utc(),
    )
    session.add(rotation)
    event = await append_event(
        session,
        event_type="agent.key_rotated",
        actor={"agent_id": agent_id, "device_id": current_device.device_id},
        payload={
            "rotation_id": rotation.rotation_id,
            "old_public_key": genesis.agent_public_key,
            "new_public_key": payload["new_public_key"],
        },
        trace_id=trace_id,
    )
    rotation.rotation_event_id = event.event_id
    genesis.agent_public_key = payload["new_public_key"]
    await session.commit()
    return {
        "agent_id": agent_id,
        "rotation_id": rotation.rotation_id,
        "agent_public_key": genesis.agent_public_key,
    }


async def lineage(session: AsyncSession, agent_id: str) -> dict[str, Any]:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise AuthRequired("Agent not found.")
    genesis = await session.get(AgentGenesis, agent_id)
    devices = (
        await session.execute(select(Device).where(Device.agent_id == agent_id))
    ).scalars().all()
    authorizations = (
        await session.execute(
            select(AgentDeviceAuthorization).where(AgentDeviceAuthorization.agent_id == agent_id)
        )
    ).scalars().all()
    rotations = (
        await session.execute(select(AgentKeyRotation).where(AgentKeyRotation.agent_id == agent_id))
    ).scalars().all()
    events = (
        await session.execute(
            select(Event)
            .where(
                Event.actor["agent_id"].astext == agent_id,
                Event.event_type.in_([
                    "agent.genesis",
                    "agent.enrollment_attested",
                    "agent.device_authorized",
                    "agent.key_rotated",
                    "device.revoked",
                    "passport.issued",
                ]),
            )
            .order_by(Event.occurred_at)
            .limit(100)
        )
    ).scalars().all()
    auth_by_device = {a.device_id: a for a in authorizations}
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "genesis": None if genesis is None else {
            "genesis_event_id": genesis.genesis_event_id,
            "first_device_id": genesis.first_device_id,
            "constitution_hash": genesis.constitution_hash,
            "born_at": genesis.born_at.isoformat(),
        },
        "devices": [
            {
                "device_id": d.device_id,
                "status": d.status,
                "label": d.label,
                "created_at": d.created_at.isoformat(),
                "revoked_at": d.revoked_at.isoformat() if d.revoked_at else None,
                "authorization": None if d.device_id not in auth_by_device else {
                    "status": auth_by_device[d.device_id].status,
                    "assurance_level": auth_by_device[d.device_id].assurance_level,
                    "authorized_at": auth_by_device[d.device_id].authorized_at.isoformat(),
                },
            }
            for d in devices
        ],
        "key_rotations": [
            {
                "rotation_id": r.rotation_id,
                "device_id": r.device_id,
                "created_at": r.created_at.isoformat(),
                "event_id": r.rotation_event_id,
            }
            for r in rotations
        ],
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in events
        ],
        "privacy": {
            "hardware_identifiers_collected": False,
            "raw_hardware_fields": [],
        },
    }


async def create_installation_key(
    session: AsyncSession,
    *,
    device_id: str,
    installation_public_key: str,
) -> DeviceInstallationKey:
    existing = (
        await session.execute(
            select(DeviceInstallationKey).where(DeviceInstallationKey.device_id == device_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    dup = (
        await session.execute(
            select(DeviceInstallationKey).where(
                DeviceInstallationKey.public_key == installation_public_key
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise Conflict("Installation public key is already enrolled.")
    record = DeviceInstallationKey(
        installation_key_id=new_device_installation_key_id(),
        device_id=device_id,
        public_key=installation_public_key,
        status="active",
        created_at=now_utc(),
        revoked_at=None,
    )
    session.add(record)
    await session.flush()
    return record
