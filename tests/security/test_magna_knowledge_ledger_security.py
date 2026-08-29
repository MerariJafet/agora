"""MAGNA Knowledge Ledger security invariants."""

import pytest

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.security


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _agent(api_client, unique_name: str) -> dict:
    await api_client.post("/v1/world/magna/bootstrap")
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-magna-kl-sec")


async def _open_object(
    api_client, reg: dict, unique_name: str, suffix: str, object_type="evidence"
):
    response = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": object_type,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {"title": suffix},
            "idempotency_key": f"{unique_name}-{suffix}",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "secret", "api_key": "sk-test"},
        {"title": "cot", "chain_of_thought": "private reasoning"},
        {"title": "key", "private_key": "-----BEGIN PRIVATE KEY-----"},
    ],
)
async def test_secret_like_payload_rejected(api_client, unique_name, payload):
    reg = await _agent(api_client, unique_name)
    response = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": "evidence",
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": payload,
            "idempotency_key": f"{unique_name}-secret",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "knowledge_ledger_violation"


async def test_sealed_plaintext_rejected(api_client, unique_name):
    reg = await _agent(api_client, unique_name)
    response = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": "dataset",
            "visibility_lane": "SEALED",
            "rights_status": "pending_human_review",
            "payload": {"commitment_hash": "a" * 64, "plaintext": "do not store me"},
            "idempotency_key": f"{unique_name}-sealed-plaintext",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "knowledge_ledger_violation"


async def test_self_edge_rejected(api_client, unique_name):
    reg = await _agent(api_client, unique_name)
    row = await _open_object(api_client, reg, unique_name, "self-edge")
    response = await api_client.post(
        "/v1/knowledge-ledger/edges",
        json={
            "source_object_id": row["object_id"],
            "target_object_id": row["object_id"],
            "relation_type": "supports",
            "idempotency_key": f"{unique_name}-self-edge",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 422


async def test_replicated_requires_independent_controller(api_client, unique_name):
    reg = await _agent(api_client, unique_name)
    protocol = await _open_object(api_client, reg, unique_name, "protocol", "registered_protocol")
    outcome = await _open_object(api_client, reg, unique_name, "outcome", "outcome")
    evidence = await _open_object(api_client, reg, unique_name, "evidence", "evidence")
    replication = await _open_object(api_client, reg, unique_name, "replication", "replication")
    response = await api_client.post(
        "/v1/knowledge-ledger/resolution-receipts",
        json={
            "challenge_id": "chg_00000000000000000000000000",
            "outcome_id": outcome["object_id"],
            "registered_protocol_id": protocol["object_id"],
            "requested_state": "REPLICATED",
            "evidence_object_ids": [evidence["object_id"]],
            "replication_object_ids": [replication["object_id"]],
            "idempotency_key": f"{unique_name}-replicated",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision"] == "rejected"
    assert "independent_controller_requirement_not_met" in body["reason_codes"]
    assert body["payment_eligible"] is False
