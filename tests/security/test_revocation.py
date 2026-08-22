"""Sprint 01.1 revocation security tests (S1.1-T03)."""

from datetime import UTC, datetime, timedelta

import pytest
from agora_api.db import session_factory
from agora_api.models import Event
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _revoke_signature(keypair: SigningKeypair, device_id: str, timestamp: str) -> str:
    return keypair.sign_b64(f"agora.revoke.v1|{device_id}|{timestamp}".encode())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


async def test_unauthenticated_revoke_rejected(api_client, keypair, unique_name):
    """Knowing a public device_id is never enough to revoke it."""
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(f"/v1/devices/{reg['device_id']}/revoke")
    assert r.status_code == 401
    # device untouched
    detail = (await api_client.get(f"/v1/agents/{reg['agent_id']}")).json()
    assert detail["devices"][0]["status"] == "authorized"


async def test_device_cannot_revoke_other_device(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    reg_a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    reg_b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    r = await api_client.post(
        f"/v1/devices/{reg_b['device_id']}/revoke",
        headers={"Authorization": f"Bearer {reg_a['session_token']}"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "owner_authority_required"
    detail = (await api_client.get(f"/v1/agents/{reg_b['agent_id']}")).json()
    assert detail["devices"][0]["status"] == "authorized"


async def test_session_self_revoke_succeeds(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        f"/v1/devices/{reg['device_id']}/revoke",
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"


async def test_signed_self_revoke_and_idempotency(api_client, keypair, unique_name):
    """Signed revocation works without any session and repeating it is safe."""
    reg = await register_agent(api_client, keypair, unique_name)
    ts = _now_iso()
    body = {
        "device_id": reg["device_id"],
        "timestamp": ts,
        "signature": _revoke_signature(keypair, reg["device_id"], ts),
    }
    first = await api_client.post("/v1/devices/revoke-signed", json=body)
    assert first.status_code == 200
    assert first.json() == {
        "device_id": reg["device_id"], "status": "revoked", "already_revoked": False,
    }
    second = await api_client.post("/v1/devices/revoke-signed", json=body)
    assert second.status_code == 200
    assert second.json()["already_revoked"] is True

    # device.revoked appended exactly once at the logical level
    async with session_factory()() as session:
        count = (
            await session.execute(
                select(func.count()).where(
                    Event.event_type == "device.revoked",
                    Event.actor["device_id"].astext == reg["device_id"],
                )
            )
        ).scalar_one()
        assert count == 1


async def test_signed_revoke_wrong_key_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    attacker = SigningKeypair()
    ts = _now_iso()
    r = await api_client.post(
        "/v1/devices/revoke-signed",
        json={
            "device_id": reg["device_id"],
            "timestamp": ts,
            "signature": _revoke_signature(attacker, reg["device_id"], ts),
        },
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "signature_invalid"


async def test_signed_revoke_stale_timestamp_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    stale = (datetime.now(UTC) - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    r = await api_client.post(
        "/v1/devices/revoke-signed",
        json={
            "device_id": reg["device_id"],
            "timestamp": stale,
            "signature": _revoke_signature(keypair, reg["device_id"], stale),
        },
    )
    assert r.status_code == 401


async def test_revoked_device_cannot_renew_auth_material(api_client, keypair, unique_name):
    """The registration idempotency replay path must not mint fresh sessions
    for a revoked device (refresh cannot revive revocation)."""
    from agora_api.crypto import registration_message

    reg = await register_agent(api_client, keypair, unique_name)
    revoke = await api_client.post(
        f"/v1/devices/{reg['device_id']}/revoke",
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert revoke.status_code == 200

    challenge = reg["_challenge"]
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
            "idempotency_key": reg["_idempotency_key"],  # exact original key
        },
    )
    assert replay.status_code == 403
    assert replay.json()["error"]["code"] == "device_revoked"


async def test_revoked_device_all_authenticated_paths_denied(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    token = reg["session_token"]
    r = await api_client.post(
        f"/v1/devices/{reg['device_id']}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    # every authenticated surface goes through the shared authz dependency
    ping = await api_client.post(
        "/v1/devices/ping", headers={"Authorization": f"Bearer {token}"}
    )
    assert ping.status_code == 403
    again = await api_client.post(
        f"/v1/devices/{reg['device_id']}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert again.status_code == 403  # documented safe result for session path
    assert again.json()["error"]["code"] == "device_revoked"