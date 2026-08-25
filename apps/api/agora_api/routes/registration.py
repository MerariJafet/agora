"""Registration vertical slice (S1-T06/T07).

Flow:
  1. POST /v1/registration/challenge  -> single-use, expiring challenge
  2. Bridge signs canonical message locally (private key never leaves edge)
  3. POST /v1/registration/register   -> verify signature, create Agent +
     AgentVersion + Device transactionally, append agent.registered and
     device.authorized ledger events + outbox rows, return public ids and a
     short-lived session token.

Security notes:
- Challenge consumption uses a conditional UPDATE ... WHERE consumed_at IS
  NULL so concurrent replays race on the row and exactly one wins (SEC-004/005).
- Idempotency: same idempotency_key returns the original public identifiers
  (fresh session token — tokens are never stored in plaintext) instead of a
  duplicate registration.
- The request schema structurally cannot carry provider credentials or key
  material; unknown fields are rejected (additionalProperties: false).
"""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.auth import auth_provider
from agora_api.boundary import validate_challenge_request, validate_register_request
from agora_api.config import get_settings
from agora_api.crypto import b64url_encode, registration_message, verify_signature
from agora_api.db import get_session
from agora_api.errors import ChallengeInvalid, Conflict, SignatureInvalid
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_agent_id,
    new_agent_version_id,
    new_challenge_id,
    new_device_id,
)
from agora_api.logging import get_logger
from agora_api.models import (
    Agent,
    AgentVersion,
    Device,
    IdempotencyRecord,
    RegistrationChallenge,
)
from agora_api.passports_service import ensure_authorization, ensure_genesis
from agora_api.provenance import add_provenance
from agora_api.ratelimit import enforce_rate_limit
from agora_api.tokoins_service import wallet_for_agent

router = APIRouter(prefix="/v1/registration", tags=["registration"])
log = get_logger("agora.api.registration")


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/challenge", status_code=201)
async def create_challenge(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    await enforce_rate_limit("reg_challenge", _client_key(request))
    body = await request.json()
    validate_challenge_request(body)

    challenge = RegistrationChallenge(
        challenge_id=new_challenge_id(),
        nonce=b64url_encode(secrets.token_bytes(32)),
        public_key=body["public_key"],
        agent_name=body["agent_name"],
        expires_at=now_utc() + timedelta(seconds=get_settings().challenge_ttl_seconds),
        consumed_at=None,
        created_at=now_utc(),
    )
    session.add(challenge)
    await session.commit()
    return {
        "challenge_id": challenge.challenge_id,
        "nonce": challenge.nonce,
        "expires_at": challenge.expires_at.isoformat().replace("+00:00", "Z"),
    }


@router.post("/register", status_code=201)
async def register(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    await enforce_rate_limit("reg_register", _client_key(request))
    body = await request.json()
    validate_register_request(body)

    # Idempotent replay: return stored public identifiers with a fresh session.
    existing = await session.get(
        IdempotencyRecord, {"idempotency_key": body["idempotency_key"], "endpoint": "register"}
    )
    if existing is not None:
        stored = dict(existing.response_body)
        token, expires_at = await auth_provider.issue_session(session, stored["device_id"])
        await session.commit()
        stored["session_token"] = token
        stored["session_expires_at"] = expires_at
        return stored

    challenge = await session.get(RegistrationChallenge, body["challenge_id"])
    if challenge is None:
        raise ChallengeInvalid("Unknown challenge.")
    if challenge.expires_at <= now_utc():
        raise ChallengeInvalid("Challenge expired.")
    if challenge.public_key != body["public_key"] or challenge.agent_name != body["agent_name"]:
        raise ChallengeInvalid("Challenge does not match this key/agent.")

    message = registration_message(
        challenge.challenge_id, challenge.nonce, body["public_key"], body["agent_name"]
    )
    if not verify_signature(body["public_key"], message, body["signature"]):
        raise SignatureInvalid("Signature verification failed.")

    # Single-use consumption: conditional update, exactly one concurrent winner.
    result = await session.execute(
        update(RegistrationChallenge)
        .where(
            RegistrationChallenge.challenge_id == challenge.challenge_id,
            RegistrationChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=now_utc())
    )
    if getattr(result, "rowcount", 0) != 1:
        raise ChallengeInvalid("Challenge already used.")

    duplicate = await session.execute(select(Agent).where(Agent.name == body["agent_name"]))
    if duplicate.scalar_one_or_none() is not None:
        raise Conflict("An agent with this name already exists.")
    dup_key = await session.execute(
        select(Device).where(Device.public_key == body["public_key"])
    )
    if dup_key.scalar_one_or_none() is not None:
        raise Conflict("This device key is already registered.")

    ts = now_utc()
    agent = Agent(
        agent_id=new_agent_id(),
        name=body["agent_name"],
        status="registered",
        created_at=ts,
        updated_at=ts,
    )
    version = AgentVersion(
        agent_version_id=new_agent_version_id(),
        agent_id=agent.agent_id,
        version=1,
        description="Initial registration",
        created_at=ts,
    )
    agent.current_version_id = version.agent_version_id
    device = Device(
        device_id=new_device_id(),
        agent_id=agent.agent_id,
        public_key=body["public_key"],
        label=body.get("device_label"),
        status="authorized",
        created_at=ts,
    )
    session.add_all([agent, version, device])
    await add_provenance(
        session,
        record_table="agents",
        record_id=agent.agent_id,
        created_by="registration.register",
        source_reference=body["idempotency_key"],
    )
    await add_provenance(
        session,
        record_table="devices",
        record_id=device.device_id,
        created_by="registration.register",
        source_reference=agent.agent_id,
    )

    trace_id = getattr(request.state, "trace_id", None)
    actor = {"agent_id": agent.agent_id, "agent_version_id": version.agent_version_id,
             "device_id": device.device_id}
    registered = await append_event(
        session,
        event_type="agent.registered",
        actor=actor,
        payload={"agent_id": agent.agent_id, "name": agent.name,
                 "agent_version_id": version.agent_version_id},
        correlation_id=body["idempotency_key"],
        trace_id=trace_id,
    )
    await append_event(
        session,
        event_type="device.authorized",
        actor=actor,
        payload={"device_id": device.device_id, "agent_id": agent.agent_id,
                 "public_key": body["public_key"]},
        correlation_id=body["idempotency_key"],
        causation_id=registered.event_id,
        trace_id=trace_id,
    )
    await ensure_authorization(
        session,
        agent_id=agent.agent_id,
        device_id=device.device_id,
        assurance_level="device",
    )
    await ensure_genesis(session, agent=agent, device=device, trace_id=trace_id)
    wallet = await wallet_for_agent(
        session,
        agent.agent_id,
        create=True,
        trace_id=trace_id,
    )

    public_response = {
        "agent_id": agent.agent_id,
        "agent_version_id": version.agent_version_id,
        "device_id": device.device_id,
        "wallet_id": wallet.wallet_id,
    }
    session.add(
        IdempotencyRecord(
            idempotency_key=body["idempotency_key"],
            endpoint="register",
            response_body=public_response,
            created_at=ts,
        )
    )
    token, expires_at = await auth_provider.issue_session(session, device.device_id)
    await session.commit()

    log.info("registration.completed", agent_id=agent.agent_id, device_id=device.device_id)
    return {**public_response, "session_token": token, "session_expires_at": expires_at}


@router.post("/claim")
async def consume_claim(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    """Device-side half of the ownership pairing (S2-T04). Requires BOTH the
    one-time code (proves the human owner initiated it) and an Ed25519
    signature by the agent's device key (proves device possession). Single
    use, expiring, cross-owner-safe, replay-safe."""
    import hashlib

    from agora_api.models import ClaimChallenge

    await enforce_rate_limit("reg_claim", _client_key(request))
    body = await request.json()
    if not isinstance(body, dict):
        raise ChallengeInvalid("Malformed claim.")
    agent_id, code = body.get("agent_id"), body.get("code")
    device_id, signature = body.get("device_id"), body.get("signature")
    if (
        not isinstance(agent_id, str) or not agent_id
        or not isinstance(code, str) or not code
        or not isinstance(device_id, str) or not device_id
        or not isinstance(signature, str) or not signature
    ):
        raise ChallengeInvalid("Malformed claim.")

    claim = (
        await session.execute(
            select(ClaimChallenge).where(
                ClaimChallenge.code_hash == hashlib.sha256(code.encode()).hexdigest()
            )
        )
    ).scalar_one_or_none()
    if claim is None or claim.agent_id != agent_id:
        raise ChallengeInvalid("Unknown claim code.")
    if claim.expires_at <= now_utc():
        raise ChallengeInvalid("Claim code expired.")

    device = await session.get(Device, device_id)
    if device is None or device.agent_id != agent_id or device.status != "authorized":
        raise ChallengeInvalid("Device cannot prove this agent.")
    from agora_api.owners import claim_message

    if not verify_signature(device.public_key, claim_message(agent_id, code), signature):
        raise SignatureInvalid("Claim signature verification failed.")

    # Single-use consumption (replay-safe, one concurrent winner).
    consumed = await session.execute(
        update(ClaimChallenge)
        .where(ClaimChallenge.claim_id == claim.claim_id, ClaimChallenge.consumed_at.is_(None))
        .values(consumed_at=now_utc())
    )
    if getattr(consumed, "rowcount", 0) != 1:
        raise ChallengeInvalid("Claim code already used.")

    agent = await session.get(Agent, agent_id)
    assert agent is not None
    if agent.owner_id is not None:
        raise Conflict("Agent is already owned.")
    agent.owner_id = claim.user_id
    agent.updated_at = now_utc()
    await append_event(
        session,
        event_type="agent.claimed",
        actor={"agent_id": agent_id, "device_id": device_id},
        payload={"agent_id": agent_id, "owner_id": claim.user_id},
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    log.info("claim.completed", agent_id=agent_id, owner_id=claim.user_id)
    return {"agent_id": agent_id, "owner_id": claim.user_id, "claimed": True}
