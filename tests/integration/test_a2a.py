"""A2A cards, registry, relay and task lifecycle (S2-T14/15/16/18)."""

import secrets

import pytest
from sqlalchemy import select

from agora_api.a2a_service import (
    artifact_hash,
    complete_task,
    pending_tasks_for,
    validate_agent_card,
)
from agora_api.db import session_factory
from agora_api.errors import AgoraError
from agora_api.models import A2ATask
from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration

PLAZA = "spc_00000000000000000000P1AZA0"


def _wire_message(text: str) -> dict:
    return {
        "messageId": f"msg-{secrets.token_hex(6)}",
        "role": "ROLE_USER",
        "parts": [{"text": text}],
    }


async def _send(api_client, token: str, target: str, message: dict) -> dict:
    r = await api_client.post(
        f"/v1/a2a/agents/{target}/jsonrpc",
        json={"jsonrpc": "2.0", "id": 1, "method": "message/send",
              "params": {"message": message}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_agent_card_valid_and_discoverable(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    card_resp = (await api_client.get(f"/v1/a2a/agents/{reg['agent_id']}/card")).json()
    card = card_resp["card"]
    assert card["name"] == unique_name
    assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"
    assert any(s["id"] == "first_contact" for s in card["skills"])
    validate_agent_card(card)  # strict official-SDK validation
    # AGORA metadata is beside the card, not inside it
    assert "agora" in card_resp and "agent_id" not in card

    registry = (await api_client.get("/v1/a2a/agents")).json()
    assert reg["agent_id"] in [a["agent_id"] for a in registry["agents"]]


async def test_malformed_agent_card_rejected(api_client):
    bogus = {"name": "Evil", "version": "1", "bogusField": {"x": 1}}
    r = await api_client.post("/v1/a2a/validate-card", json=bogus)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "a2a_invalid"
    with pytest.raises(AgoraError):
        validate_agent_card({"description": "no name or version"})


async def test_registry_space_filter(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    listed = (await api_client.get("/v1/a2a/agents", params={"space_id": PLAZA})).json()
    assert reg["agent_id"] not in [a["agent_id"] for a in listed["agents"]]
    await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    listed = (await api_client.get("/v1/a2a/agents", params={"space_id": PLAZA})).json()
    assert reg["agent_id"] in [a["agent_id"] for a in listed["agents"]]


async def test_offline_target_task_stays_submitted_and_pending(api_client, unique_name):
    kp_i, kp_t = SigningKeypair(), SigningKeypair()
    initiator = await register_agent(api_client, kp_i, f"{unique_name}-I")
    target = await register_agent(api_client, kp_t, f"{unique_name}-T")
    response = await _send(
        api_client, initiator["session_token"], target["agent_id"], _wire_message("hello")
    )
    task = response["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_SUBMITTED"
    async with session_factory()() as session:
        pending = await pending_tasks_for(session, target["agent_id"])
        assert task["id"] in [t.task_id for t in pending]
        row = await session.get(A2ATask, task["id"])
        assert row.nonce and len(row.nonce) == 32  # server-issued nonce


async def test_malformed_wire_message_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        f"/v1/a2a/agents/{reg['agent_id']}/jsonrpc",
        json={"jsonrpc": "2.0", "id": 1, "method": "message/send",
              "params": {"message": {"messageId": "m", "hostileField": True}}},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "a2a_invalid"


async def test_duplicate_completion_is_idempotent(api_client, unique_name):
    """SEC-009: duplicate relay results produce ONE logical completion."""
    kp_i, kp_t = SigningKeypair(), SigningKeypair()
    initiator = await register_agent(api_client, kp_i, f"{unique_name}-I")
    target = await register_agent(api_client, kp_t, f"{unique_name}-T")
    response = await _send(
        api_client, initiator["session_token"], target["agent_id"], _wire_message("dup test")
    )
    task_id = response["result"]["task"]["id"]
    artifact = {
        "artifactId": f"art-{task_id}",
        "name": "First Contact Note",
        "parts": [{"text": '{"ok": true}', "mediaType": "application/json"}],
    }
    async with session_factory()() as session:
        assert await complete_task(session, task_id, [artifact]) is True
    async with session_factory()() as session:
        assert await complete_task(session, task_id, [artifact]) is False  # duplicate ignored

    poll = await api_client.post(
        f"/v1/a2a/agents/{target['agent_id']}/jsonrpc",
        json={"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": task_id}},
        headers={"Authorization": f"Bearer {initiator['session_token']}"},
    )
    task = poll.json()["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert len(task["artifacts"]) == 1
    assert artifact_hash(artifact)  # integrity hash computable


async def test_malformed_artifact_rejected(api_client, unique_name):
    kp_i, kp_t = SigningKeypair(), SigningKeypair()
    initiator = await register_agent(api_client, kp_i, f"{unique_name}-I")
    target = await register_agent(api_client, kp_t, f"{unique_name}-T")
    response = await _send(
        api_client, initiator["session_token"], target["agent_id"], _wire_message("bad artifact")
    )
    task_id = response["result"]["task"]["id"]
    async with session_factory()() as session:
        with pytest.raises(AgoraError):
            await complete_task(
                session, task_id, [{"artifactId": "a", "evilField": "x"}]
            )


async def test_task_access_restricted_to_participants(api_client, unique_name):
    kp_i, kp_t, kp_x = SigningKeypair(), SigningKeypair(), SigningKeypair()
    initiator = await register_agent(api_client, kp_i, f"{unique_name}-I")
    target = await register_agent(api_client, kp_t, f"{unique_name}-T")
    stranger = await register_agent(api_client, kp_x, f"{unique_name}-X")
    response = await _send(
        api_client, initiator["session_token"], target["agent_id"], _wire_message("private")
    )
    task_id = response["result"]["task"]["id"]
    r = await api_client.post(
        f"/v1/a2a/agents/{target['agent_id']}/jsonrpc",
        json={"jsonrpc": "2.0", "id": 3, "method": "tasks/get", "params": {"id": task_id}},
        headers={"Authorization": f"Bearer {stranger['session_token']}"},
    )
    assert r.status_code == 404


async def test_unauthenticated_rpc_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        f"/v1/a2a/agents/{reg['agent_id']}/jsonrpc",
        json={"jsonrpc": "2.0", "id": 1, "method": "message/send",
              "params": {"message": _wire_message("anon")}},
    )
    assert r.status_code == 401


async def test_unsupported_method_gets_jsonrpc_error(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        f"/v1/a2a/agents/{reg['agent_id']}/jsonrpc",
        json={"jsonrpc": "2.0", "id": 9, "method": "message/stream", "params": {}},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32601