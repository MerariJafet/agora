"""Post-roadmap Sprint 1 lineage/passport security tests."""

from datetime import timedelta

import pytest
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.ids import new_device_id
from agora_api.models import AgentDeviceAuthorization, AgentGenesis, Device, Event, PassportSession
from agora_api.passports_service import (
    canonical_json,
    enrollment_message,
    passport_issue_message,
    rotation_message,
)
from sqlalchemy import select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.security


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _registered(api_client, unique_name: str):
    keypair = SigningKeypair()
    reg = await register_agent(api_client, keypair, f"{unique_name}-lineage")
    return keypair, reg


async def _issue_passport(api_client, keypair: SigningKeypair, reg: dict):
    ts = now_utc().isoformat().replace("+00:00", "Z")
    message = passport_issue_message(reg["agent_id"], reg["device_id"], ts)
    return await api_client.post(
        "/v1/passports/issue",
        json={
            "agent_id": reg["agent_id"],
            "device_id": reg["device_id"],
            "timestamp": ts,
            "signature": keypair.sign_b64(message),
        },
    )


async def test_registration_creates_one_canonical_genesis(api_client, unique_name):
    _keypair, reg = await _registered(api_client, unique_name)

    async with session_factory()() as session:
        rows = (
            await session.execute(
                select(AgentGenesis).where(AgentGenesis.agent_id == reg["agent_id"])
            )
        ).scalars().all()
        assert len(rows) == 1
        events = (
            await session.execute(
                select(Event).where(
                    Event.event_type == "agent.genesis",
                    Event.actor["agent_id"].astext == reg["agent_id"],
                )
            )
        ).scalars().all()
        assert len(events) == 1


async def test_enrollment_replay_is_rejected(api_client, unique_name):
    keypair, reg = await _registered(api_client, unique_name)
    challenge = (
        await api_client.post(
            "/v1/enrollment/challenge",
            json={"agent_id": reg["agent_id"], "device_id": reg["device_id"]},
        )
    ).json()
    message = enrollment_message(
        challenge["challenge_id"],
        challenge["nonce"],
        reg["agent_id"],
        reg["device_id"],
        challenge["constitution_hash"],
    )
    payload = {
        "challenge_id": challenge["challenge_id"],
        "agent_id": reg["agent_id"],
        "device_id": reg["device_id"],
        "device_signature": keypair.sign_b64(message),
        "agent_signature": keypair.sign_b64(message),
    }
    first = await api_client.post("/v1/enrollment/attest", json=payload)
    replay = await api_client.post("/v1/enrollment/attest", json=payload)

    assert first.status_code == 200
    assert first.json()["classification"] == "KNOWN_AGENT_KNOWN_DEVICE"
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "challenge_invalid"


async def test_passport_issues_and_verifies_for_known_agent_known_device(api_client, unique_name):
    keypair, reg = await _registered(api_client, unique_name)
    issued = await _issue_passport(api_client, keypair, reg)
    assert issued.status_code == 201, issued.text

    token = issued.json()["passport_token"]
    verified = await api_client.post("/v1/passports/verify", json={"passport_token": token})

    assert verified.status_code == 200, verified.text
    assert verified.json()["agent_id"] == reg["agent_id"]
    assert issued.json()["passport"]["constitution_hash"]
    assert "world.enter" in issued.json()["passport"]["scopes"]


async def test_passport_canonical_json_is_stable():
    assert canonical_json({"b": 2, "a": {"z": True, "m": [3, 1]}}) == (
        '{"a":{"m":[3,1],"z":true},"b":2}'
    )
    assert passport_issue_message("agt_abc", "dev_xyz", "2026-08-25T00:00:00Z") == (
        b"agora.passport.issue.v1|agt_abc|dev_xyz|2026-08-25T00:00:00Z"
    )


async def test_unauthorized_device_cannot_receive_ordinary_passport(api_client, unique_name):
    _keypair, reg = await _registered(api_client, unique_name)
    other_key = SigningKeypair()
    device_id = new_device_id()
    async with session_factory()() as session:
        session.add(
            Device(
                device_id=device_id,
                agent_id=reg["agent_id"],
                public_key=other_key.public_key_b64,
                label="unauthorized-test-device",
                status="authorized",
                created_at=now_utc(),
                revoked_at=None,
            )
        )
        await session.commit()

    ts = now_utc().isoformat().replace("+00:00", "Z")
    response = await api_client.post(
        "/v1/passports/issue",
        json={
            "agent_id": reg["agent_id"],
            "device_id": device_id,
            "timestamp": ts,
            "signature": other_key.sign_b64(
                passport_issue_message(reg["agent_id"], device_id, ts)
            ),
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


async def test_revoked_device_signatures_are_rejected_for_passport(api_client, unique_name):
    keypair, reg = await _registered(api_client, unique_name)
    revoke = await api_client.post(
        f"/v1/agents/{reg['agent_id']}/devices/{reg['device_id']}/revoke",
        headers=_auth(reg),
    )
    assert revoke.status_code == 200

    response = await _issue_passport(api_client, keypair, reg)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "device_revoked"


async def test_agent_key_rotation_requires_old_and_new_key_possession(api_client, unique_name):
    keypair, reg = await _registered(api_client, unique_name)
    new_keypair = SigningKeypair()
    ts = now_utc().isoformat().replace("+00:00", "Z")
    message = rotation_message(
        reg["agent_id"], keypair.public_key_b64, new_keypair.public_key_b64, ts
    )

    rotated = await api_client.post(
        f"/v1/agents/{reg['agent_id']}/keys/rotate",
        json={
            "new_public_key": new_keypair.public_key_b64,
            "timestamp": ts,
            "old_key_signature": keypair.sign_b64(message),
            "new_key_signature": new_keypair.sign_b64(message),
        },
        headers=_auth(reg),
    )

    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["agent_public_key"] == new_keypair.public_key_b64

    async with session_factory()() as session:
        genesis = await session.get(AgentGenesis, reg["agent_id"])
    assert genesis is not None
    assert genesis.agent_public_key == new_keypair.public_key_b64


async def test_agent_key_rotation_rejects_missing_new_key_proof(api_client, unique_name):
    keypair, reg = await _registered(api_client, unique_name)
    new_keypair = SigningKeypair()
    attacker = SigningKeypair()
    ts = now_utc().isoformat().replace("+00:00", "Z")
    message = rotation_message(
        reg["agent_id"], keypair.public_key_b64, new_keypair.public_key_b64, ts
    )

    rejected = await api_client.post(
        f"/v1/agents/{reg['agent_id']}/keys/rotate",
        json={
            "new_public_key": new_keypair.public_key_b64,
            "timestamp": ts,
            "old_key_signature": keypair.sign_b64(message),
            "new_key_signature": attacker.sign_b64(message),
        },
        headers=_auth(reg),
    )

    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "auth_required"


async def test_expired_passport_is_rejected(api_client, unique_name):
    keypair, reg = await _registered(api_client, unique_name)
    issued = await _issue_passport(api_client, keypair, reg)
    token = issued.json()["passport_token"]

    async with session_factory()() as session:
        row = (
            await session.execute(
                select(PassportSession).where(
                    PassportSession.passport_id == issued.json()["passport"]["passport_id"]
                )
            )
        ).scalar_one()
        row.expires_at = now_utc() - timedelta(seconds=1)
        await session.commit()

    verified = await api_client.post("/v1/passports/verify", json={"passport_token": token})
    assert verified.status_code == 401
    assert verified.json()["error"]["code"] == "passport_rejected"


async def test_lineage_contains_no_raw_hardware_identifiers(api_client, unique_name):
    _keypair, reg = await _registered(api_client, unique_name)

    lineage = await api_client.get(f"/v1/agents/{reg['agent_id']}/lineage")
    payload = lineage.json()
    raw = str(payload).lower()

    assert lineage.status_code == 200
    assert payload["privacy"]["hardware_identifiers_collected"] is False
    forbidden = ["mac", "machine-id", "machine_id", "disk serial", "tpm", "hostname"]
    assert all(marker not in raw for marker in forbidden)


async def test_location_style_state_cannot_duplicate_birth_event(api_client, unique_name):
    _keypair, reg = await _registered(api_client, unique_name)
    before = (
        await api_client.get(f"/v1/agents/{reg['agent_id']}/events")
    ).json()["events"]

    for _ in range(5):
        entered = await api_client.post(
            "/v1/spaces/spc_00000000000000000000P1AZA0/enter",
            headers=_auth(reg),
        )
        assert entered.status_code == 200

    async with session_factory()() as session:
        events = (
            await session.execute(
                select(Event).where(
                    Event.event_type == "agent.genesis",
                    Event.actor["agent_id"].astext == reg["agent_id"],
                )
            )
        ).scalars().all()
        auth = await session.get(AgentDeviceAuthorization, (reg["agent_id"], reg["device_id"]))

    assert len(events) == 1
    assert auth is not None and auth.status == "authorized"
    assert before
