"""MAGNA Sprint 04 TOKOIN local-devnet integration tests."""

import hashlib

import pytest

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


def _controller(label: str) -> str:
    return hashlib.sha256(f"controller:{label}".encode()).hexdigest()


def _address(label: str) -> str:
    return "0x" + hashlib.sha256(f"wallet:{label}".encode()).hexdigest()[:40]


async def _agent(api_client, unique_name: str, suffix: str) -> dict:
    await api_client.post("/v1/world/magna/bootstrap")
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-{suffix}")


async def _knowledge_object(
    api_client, reg: dict, unique_name: str, suffix: str, kind: str
) -> dict:
    response = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": kind,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {"fixture": suffix},
            "idempotency_key": f"{unique_name}-{suffix}",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _accepted_receipt(api_client, reg: dict, unique_name: str, challenge_id: str) -> dict:
    protocol = await _knowledge_object(
        api_client, reg, unique_name, "protocol", "registered_protocol"
    )
    outcome = await _knowledge_object(api_client, reg, unique_name, "outcome", "outcome")
    evidence = await _knowledge_object(api_client, reg, unique_name, "evidence", "evidence")
    response = await api_client.post(
        "/v1/knowledge-ledger/resolution-receipts",
        json={
            "challenge_id": challenge_id,
            "outcome_id": outcome["object_id"],
            "registered_protocol_id": protocol["object_id"],
            "requested_state": "RESOLVED_VERIFIED",
            "evidence_object_ids": [evidence["object_id"]],
            "idempotency_key": f"{unique_name}-receipt",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    assert response.json()["decision"] == "accepted"
    assert response.json()["payment_eligible"] is False
    return response.json()


async def test_local_devnet_manifest_has_fixed_supply_and_no_public_deployment(api_client):
    response = await api_client.post("/v1/tokoin-testnet/deployment/local-devnet")
    assert response.status_code == 201, response.text
    manifest = response.json()
    assert manifest["chain_id"] == 31337
    assert manifest["classification"] == "LOCAL_DEVNET_TEST_ONLY_NO_ECONOMIC_VALUE"
    assert manifest["total_supply_atomic"] == "100000000000000"
    assert manifest["decimals"] == 8
    assert manifest["openzeppelin_version"] == "5.6.1"
    assert manifest["source_verified"] is True
    assert manifest["bytecode_verified"] is False
    assert manifest["mainnet_transactions"] == 0
    assert manifest["real_value_moved"] is False


@pytest.mark.parametrize("chain_id", [1, 8453, 999999, 84532])
async def test_deployment_guard_blocks_mainnet_unknown_and_unratified_base_sepolia(
    api_client, chain_id: int
):
    response = await api_client.post(
        "/v1/tokoin-testnet/deployment/guard", json={"chain_id": chain_id}
    )
    assert response.status_code in {403, 422}


async def test_agent_wallet_binding_is_receive_only_zero_balance_and_self_scoped(
    api_client, unique_name
):
    owner = await _agent(api_client, unique_name, "wallet-owner")
    other = await _agent(api_client, unique_name, "wallet-other")
    cross = await api_client.post(
        "/v1/tokoin-testnet/wallet-bindings",
        json={
            "agent_id": other["agent_id"],
            "wallet_address": _address("cross"),
            "controller_commitment_hash": _controller("cross"),
        },
        headers=_auth(owner),
    )
    assert cross.status_code == 403

    response = await api_client.post(
        "/v1/tokoin-testnet/wallet-bindings",
        json={
            "agent_id": owner["agent_id"],
            "wallet_address": _address(unique_name),
            "controller_commitment_hash": _controller(unique_name),
        },
        headers=_auth(owner),
    )
    assert response.status_code == 201, response.text
    binding = response.json()
    assert binding["state"] == "TESTNET_RECEIVE_ONLY"
    assert binding["balance_cache_atomic"] == "0"
    assert binding["balance_cache_authoritative"] is False
    again = await api_client.post(
        "/v1/tokoin-testnet/wallet-bindings",
        json={
            "agent_id": owner["agent_id"],
            "wallet_address": _address(unique_name),
            "controller_commitment_hash": _controller(unique_name),
        },
        headers=_auth(owner),
    )
    assert again.status_code == 201
    assert again.json()["binding_id"] == binding["binding_id"]


async def test_reservation_is_idempotent_and_one_tokoin_only(api_client, unique_name):
    payload = {
        "world_instance_id": "magna-local",
        "challenge_id": f"challenge-{unique_name}",
        "candidate_id": "candidate-a",
        "idempotency_key": f"{unique_name}-reservation-idem",
    }
    first = await api_client.post("/v1/tokoin-testnet/reservations", json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["state"] == "RESERVATION_REQUESTED"
    assert first.json()["amount_atomic"] == "100000000"
    second = await api_client.post("/v1/tokoin-testnet/reservations", json=payload)
    assert second.status_code == 201
    assert second.json()["reservation_id"] == first.json()["reservation_id"]
    conflict = await api_client.post(
        "/v1/tokoin-testnet/reservations",
        json=payload | {"candidate_id": "candidate-b", "idempotency_key": f"{unique_name}-other"},
    )
    assert conflict.status_code == 409


async def test_settlement_requires_reserved_valid_resolution_receipt_and_respects_caps(
    api_client, unique_name
):
    agent = await _agent(api_client, unique_name, "settlement")
    binding_response = await api_client.post(
        "/v1/tokoin-testnet/wallet-bindings",
        json={
            "agent_id": agent["agent_id"],
            "wallet_address": _address(f"{unique_name}-settlement"),
            "controller_commitment_hash": _controller("settlement"),
        },
        headers=_auth(agent),
    )
    binding = binding_response.json()
    challenge_id = "chg_s4_settlement"
    reservation = (
        await api_client.post(
            "/v1/tokoin-testnet/reservations",
            json={
                "world_instance_id": "magna-local",
                "challenge_id": challenge_id,
                "candidate_id": agent["agent_id"],
                "idempotency_key": f"{unique_name}-settlement-reservation",
            },
        )
    ).json()
    early = await api_client.post(
        "/v1/tokoin-testnet/settlement-plans",
        json={
            "reservation_id": reservation["reservation_id"],
            "resolution_receipt_id": "krr_00000000000000000000000000",
            "allocations": [],
        },
    )
    assert early.status_code in {404, 409, 422}

    confirmed = await api_client.post(
        f"/v1/tokoin-testnet/reservations/{reservation['reservation_id']}/confirm-local"
    )
    assert confirmed.status_code == 201
    assert confirmed.json()["state"] == "RESERVED"
    receipt = await _accepted_receipt(api_client, agent, unique_name, challenge_id)
    over_cap = await api_client.post(
        "/v1/tokoin-testnet/settlement-plans",
        json={
            "reservation_id": reservation["reservation_id"],
            "resolution_receipt_id": receipt["receipt_id"],
            "allocations": [
                {
                    "agent_id": agent["agent_id"],
                    "role": "proposer",
                    "amount_atomic": "1000001",
                    "wallet_binding_id": binding["binding_id"],
                    "controller_commitment_hash": _controller("settlement"),
                }
            ],
        },
    )
    assert over_cap.status_code == 422

    plan_payload = {
        "reservation_id": reservation["reservation_id"],
        "resolution_receipt_id": receipt["receipt_id"],
        "allocations": [
            {
                "agent_id": agent["agent_id"],
                "role": "proposer",
                "amount_atomic": "1000000",
                "wallet_binding_id": binding["binding_id"],
                "controller_commitment_hash": _controller("settlement"),
            }
        ],
    }
    plan_response = await api_client.post("/v1/tokoin-testnet/settlement-plans", json=plan_payload)
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    assert plan["state"] == "ALLOCATED"
    assert plan["unused_return_atomic"] == "99000000"
    assert plan["real_value_moved"] is False
    again = await api_client.post("/v1/tokoin-testnet/settlement-plans", json=plan_payload)
    assert again.status_code == 201
    assert again.json()["settlement_plan_id"] == plan["settlement_plan_id"]
