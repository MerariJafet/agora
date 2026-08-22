"""Integration tests against real PostgreSQL/Redis (docker compose up)."""

import secrets
from datetime import timedelta

import pytest
from agora_api.crypto import registration_message
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.models import Event, EventOutbox, RegistrationChallenge
from sqlalchemy import select, update

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


async def test_happy_path_registration(api_client, keypair, unique_name):
    result = await register_agent(api_client, keypair, unique_name)
    assert result["_status"] == 201
    assert result["agent_id"].startswith("agt_")
    assert result["device_id"].startswith("dev_")
    assert result["session_token"].startswith("ses_")

    # ledger events + outbox rows exist
    async with session_factory()() as session:
        events = (
            (
                await session.execute(
                    select(Event).where(Event.actor["agent_id"].astext == result["agent_id"])
                )
            )
            .scalars()
            .all()
        )
        types = {e.event_type for e in events}
        assert {"agent.registered", "device.authorized"} <= types
        outbox = (
            (
                await session.execute(
                    select(EventOutbox).where(
                        EventOutbox.event_id.in_([e.event_id for e in events])
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(outbox) == len(events)


async def test_challenge_single_use(api_client, keypair, unique_name):
    result = await register_agent(api_client, keypair, unique_name)
    assert result["_status"] == 201
    challenge = result["_challenge"]
    #

    # replay the exact same signed request (SEC-005)
    message = registration_message(
        challenge["challenge_id"], challenge["nonce"], keypair.public_key_b64, unique_name
    )
    replay = await api_client.post(
        "/v1/registration/register",
        json={
            "challenge_id": challenge["challenge_id"],
            "public_key": keypair.public_key_b64,
            "agent_name": unique_name,
            "signature": keypair.sign_b64(message),
            "idempotency_key": f"replay-{secrets.token_hex(8)}",
        },
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "challenge_invalid"


async def test_challenge_expiry(api_client, keypair, unique_name):
    challenge = (
        await api_client.post(
            "/v1/registration/challenge",
            json={"public_key": keypair.public_key_b64, "agent_name": unique_name},
        )
    ).json()
    async with session_factory()() as session:
        await session.execute(
            update(RegistrationChallenge)
            .where(RegistrationChallenge.challenge_id == challenge["challenge_id"])
            .values(expires_at=now_utc() - timedelta(seconds=1))
        )
        await session.commit()
    message = registration_message(
        challenge["challenge_id"], challenge["nonce"], keypair.public_key_b64, unique_name
    )
    response = await api_client.post(
        "/v1/registration/register",
        json={
            "challenge_id": challenge["challenge_id"],
            "public_key": keypair.public_key_b64,
            "agent_name": unique_name,
            "signature": keypair.sign_b64(message),
            "idempotency_key": f"exp-{secrets.token_hex(8)}",
        },
    )
    assert response.status_code == 401


async def test_malformed_signature_rejected(api_client, keypair, unique_name):
    challenge = (
        await api_client.post(
            "/v1/registration/challenge",
            json={"public_key": keypair.public_key_b64, "agent_name": unique_name},
        )
    ).json()
    response = await api_client.post(
        "/v1/registration/register",
        json={
            "challenge_id": challenge["challenge_id"],
            "public_key": keypair.public_key_b64,
            "agent_name": unique_name,
            "signature": "C" * 86,
            "idempotency_key": f"bad-{secrets.token_hex(8)}",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "signature_invalid"
    # a bad signature must NOT consume the challenge; a valid retry succeeds
    message = registration_message(
        challenge["challenge_id"], challenge["nonce"], keypair.public_key_b64, unique_name
    )
    retry = await api_client.post(
        "/v1/registration/register",
        json={
            "challenge_id": challenge["challenge_id"],
            "public_key": keypair.public_key_b64,
            "agent_name": unique_name,
            "signature": keypair.sign_b64(message),
            "idempotency_key": f"good-{secrets.token_hex(8)}",
        },
    )
    assert retry.status_code == 201


async def test_idempotent_registration(api_client, keypair, unique_name):
    idem_key = f"idem-{secrets.token_hex(8)}"
    challenge = (
        await api_client.post(
            "/v1/registration/challenge",
            json={"public_key": keypair.public_key_b64, "agent_name": unique_name},
        )
    ).json()
    message = registration_message(
        challenge["challenge_id"], challenge["nonce"], keypair.public_key_b64, unique_name
    )
    body = {
        "challenge_id": challenge["challenge_id"],
        "public_key": keypair.public_key_b64,
        "agent_name": unique_name,
        "signature": keypair.sign_b64(message),
        "idempotency_key": idem_key,
    }
    first = await api_client.post("/v1/registration/register", json=body)
    second = await api_client.post("/v1/registration/register", json=body)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["agent_id"] == second.json()["agent_id"]
    assert first.json()["device_id"] == second.json()["device_id"]
    # fresh session material on replay, never a stored plaintext token
    assert first.json()["session_token"] != second.json()["session_token"]


async def test_duplicate_agent_name_conflict(api_client, unique_name):
    kp1, kp2 = SigningKeypair(), SigningKeypair()
    first = await register_agent(api_client, kp1, unique_name)
    assert first["_status"] == 201
    second = await register_agent(api_client, kp2, unique_name)
    assert second["_status"] == 409


async def test_unknown_wire_fields_rejected(api_client, keypair, unique_name):
    response = await api_client.post(
        "/v1/registration/challenge",
        json={
            "public_key": keypair.public_key_b64,
            "agent_name": unique_name,
            "api_key": "sk-provider-credential",
        },
    )
    assert response.status_code == 422
