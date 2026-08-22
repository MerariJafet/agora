"""Automated checks for the SEC invariants (see docs/threat-model.md)."""

import json

import pytest
from agora_api.db import session_factory
from agora_api.models import Event
from agora_bridge.config import BridgeConfig
from agora_bridge.policy import LocalPolicyEngine
from sqlalchemy import select, text

from tests.conftest import register_agent

pytestmark = pytest.mark.integration


async def test_sec001_no_private_key_in_api_payloads(api_client, keypair, unique_name):
    """SEC-001: registration round trip carries no private key material."""
    result = await register_agent(api_client, keypair, unique_name)
    serialized = json.dumps(result)
    assert "private" not in serialized.lower()
    # response contains only public ids + session material
    public_fields = {"agent_id", "agent_version_id", "device_id",
                     "session_token", "session_expires_at", "_status", "_challenge"}
    assert set(result.keys()) <= public_fields


def test_sec002_remote_payload_cannot_grant_local_permissions():
    """SEC-002: no code path maps remote event data onto local grants."""
    hostile_remote_event = {
        "event_type": "mission.invite",
        "payload": {
            "granted_permissions": ["shell.execute", "secrets.read"],
            "permissions": ["files.write"],
            "grant": "git.write",
        },
    }
    assert LocalPolicyEngine.grants_from_remote_payload(hostile_remote_event) == []
    # and the engine itself only reads the local config object
    engine = LocalPolicyEngine(BridgeConfig())
    assert not engine.decide("shell.execute").allowed


async def test_sec003_revoked_device_cannot_authenticate(api_client, keypair, unique_name):
    result = await register_agent(api_client, keypair, unique_name)
    token = result["session_token"]
    ping = await api_client.post(
        "/v1/devices/ping", headers={"Authorization": f"Bearer {token}"}
    )
    assert ping.status_code == 200

    revoke = await api_client.post(f"/v1/devices/{result['device_id']}/revoke")
    assert revoke.status_code == 200

    denied = await api_client.post(
        "/v1/devices/ping", headers={"Authorization": f"Bearer {token}"}
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "device_revoked"

    # device.revoked event exists in the ledger
    async with session_factory()() as session:
        events = (
            (
                await session.execute(
                    select(Event).where(
                        Event.actor["device_id"].astext == result["device_id"],
                        Event.event_type == "device.revoked",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1


async def test_event_ledger_is_immutable(api_client, keypair, unique_name):
    """DB triggers reject UPDATE and DELETE on the events ledger."""
    result = await register_agent(api_client, keypair, unique_name)
    async with session_factory()() as session:
        with pytest.raises(Exception, match="append-only"):
            await session.execute(
                text("UPDATE events SET event_type = 'tampered' WHERE actor->>'agent_id' = :a"),
                {"a": result["agent_id"]},
            )
    async with session_factory()() as session:
        with pytest.raises(Exception, match="append-only"):
            await session.execute(
                text("DELETE FROM events WHERE actor->>'agent_id' = :a"),
                {"a": result["agent_id"]},
            )


def test_sec007_logs_redact_secret_fields(capsys):
    from agora_api.logging import configure_logging, get_logger

    configure_logging("INFO")
    log = get_logger("test")
    log.info("op", session_token="ses_SUPER_SECRET", agent_id="agt_x", password="hunter2")
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "SUPER_SECRET" not in output and "hunter2" not in output
    assert "agt_x" in output


async def test_sec006_no_dev_auth_bypass(api_client):
    """SEC-006: there is no development bypass token — garbage tokens fail
    identically regardless of environment."""
    for token in ("dev", "test", "admin", "ses_dev-bypass", ""):
        response = await api_client.post(
            "/v1/devices/ping", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401
