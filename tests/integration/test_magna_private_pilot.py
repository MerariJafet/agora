"""MAGNA Sprint 04.4 private TOKOIN economic pilot tests."""

import hashlib

import pytest
from agora_api.config import get_settings
from agora_api.db import session_factory
from agora_api.errors import Conflict
from agora_api.magna_private_pilot import (
    ECONOMIC_PROHIBITIONS,
    genesis_100_wallet_readiness,
    require_private_pilot_environment,
)
from agora_api.models import (
    PrePublicRewardEntitlement,
    TokoinDevnetTransfer,
    TokoinPrivatePilotReceipt,
)
from sqlalchemy import func, select, text

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _operator_headers(api_client, label: str) -> dict[str, str]:
    login = await api_client.post("/v1/auth/dev/login", json={"username": label})
    assert login.status_code == 200, login.text
    return {"X-CSRF-Token": login.json()["csrf_token"]}


def _controller(label: str) -> str:
    return hashlib.sha256(f"controller:{label}".encode()).hexdigest()


def _address(label: str) -> str:
    return "0x" + hashlib.sha256(f"private-pilot-wallet:{label}".encode()).hexdigest()[:40]


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
            "payload": {"private_pilot_fixture": suffix},
            "idempotency_key": f"{unique_name}-private-pilot-{suffix}",
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
            "idempotency_key": f"{unique_name}-private-pilot-receipt",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _bind_wallet(api_client, reg: dict, label: str) -> dict:
    response = await api_client.post(
        "/v1/tokoin-testnet/wallet-bindings",
        json={
            "agent_id": reg["agent_id"],
            "wallet_address": _address(label),
            "controller_commitment_hash": _controller(label),
        },
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_private_pilot_status_get_is_read_only(api_client):
    async with session_factory()() as session:
        before_events = (
            await session.execute(
                text("select count(*) from events where event_type like 'tokoin.private_pilot.%'")
            )
        ).scalar_one()
        before_receipts = (
            await session.execute(select(func.count()).select_from(TokoinPrivatePilotReceipt))
        ).scalar_one()

    response = await api_client.get("/v1/tokoin-private-pilot/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "READY_FOR_7_AGENT_PRIVATE_PILOT"
    assert body["policy"]["mainnet_deployed"] is False
    assert body["policy"]["genesis_100_launched"] is False
    assert set(ECONOMIC_PROHIBITIONS).issubset(set(body["policy"]["prohibitions"]))
    async with session_factory()() as session:
        after_events = (
            await session.execute(
                text("select count(*) from events where event_type like 'tokoin.private_pilot.%'")
            )
        ).scalar_one()
        after_receipts = (
            await session.execute(select(func.count()).select_from(TokoinPrivatePilotReceipt))
        ).scalar_one()
    assert after_events == before_events
    assert after_receipts == before_receipts


async def test_founder_ratifications_ingest_once(api_client):
    operator = await _operator_headers(api_client, "pilot-ratification-operator")
    first = await api_client.post(
        "/v1/tokoin-private-pilot/ratifications/ingest", headers=operator
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "RATIFIED_8_OF_8"
    assert first.json()["imported"] == 8

    second = await api_client.post(
        "/v1/tokoin-private-pilot/ratifications/ingest", headers=operator
    )
    assert second.status_code == 201, second.text
    assert second.json()["imported"] == 8

    async with session_factory()() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(TokoinPrivatePilotReceipt).where(
                    TokoinPrivatePilotReceipt.receipt_type == "founder_ratification"
                )
            )
        ).scalar_one()
    assert count == 8


def test_genesis_100_wallet_readiness_is_prepared_without_activation():
    from agora_api.magna_private_pilot import GENESIS_100_ROOT

    if not GENESIS_100_ROOT.exists():
        pytest.skip("genesis-100 agent folders live only on the founder machine")
    readiness = genesis_100_wallet_readiness()
    assert readiness["agent_folder_count"] == 100
    assert readiness["unique_wallet_address_count"] == 100
    assert readiness["missing_wallet_binding_files"] == 0
    assert readiness["forbidden_env_fields_nonempty"] == []
    assert readiness["genesis_100_live_activation"] is False


def test_private_pilot_mutations_fail_closed_in_production(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AGORA_ENV", "production")
    try:
        with pytest.raises(Conflict):
            require_private_pilot_environment()
    finally:
        get_settings.cache_clear()


async def test_private_pilot_e2e_settlement_and_migration_snapshot(api_client, unique_name):
    operator = await _operator_headers(api_client, f"pilot-{unique_name}")
    agents = [
        await _agent(api_client, unique_name, "proposer"),
        await _agent(api_client, unique_name, "contributors"),
        await _agent(api_client, unique_name, "replication"),
        await _agent(api_client, unique_name, "review"),
        await _agent(api_client, unique_name, "tools"),
    ]
    bindings = [
        await _bind_wallet(api_client, reg, f"{unique_name}-{index}")
        for index, reg in enumerate(agents)
    ]
    challenge_id = "pp-" + hashlib.sha256(unique_name.encode()).hexdigest()[:16]
    reservation = (
        await api_client.post(
            "/v1/tokoin-testnet/reservations",
            json={
                "world_instance_id": "magna-private-pilot-test",
                "challenge_id": challenge_id,
                "candidate_id": agents[0]["agent_id"],
                "idempotency_key": f"{unique_name}-reservation",
            },
            headers=operator,
        )
    ).json()
    confirmed = await api_client.post(
        f"/v1/tokoin-testnet/reservations/{reservation['reservation_id']}/confirm-local",
        headers=operator,
    )
    assert confirmed.status_code == 201, confirmed.text
    receipt = await _accepted_receipt(api_client, agents[0], unique_name, challenge_id)
    plan_response = await api_client.post(
        "/v1/tokoin-testnet/settlement-plans",
        json={
            "reservation_id": reservation["reservation_id"],
            "resolution_receipt_id": receipt["receipt_id"],
            "allocations": [
                {
                    "agent_id": agents[0]["agent_id"],
                    "role": "proposer",
                    "amount_atomic": "1000000",
                    "wallet_binding_id": bindings[0]["binding_id"],
                    "controller_commitment_hash": _controller(f"{unique_name}-0"),
                },
                {
                    "agent_id": agents[1]["agent_id"],
                    "role": "contributors",
                    "amount_atomic": "59000000",
                    "wallet_binding_id": bindings[1]["binding_id"],
                    "controller_commitment_hash": _controller(f"{unique_name}-1"),
                },
                {
                    "agent_id": agents[2]["agent_id"],
                    "role": "independent_replication",
                    "amount_atomic": "25000000",
                    "wallet_binding_id": bindings[2]["binding_id"],
                    "controller_commitment_hash": _controller(f"{unique_name}-2"),
                },
                {
                    "agent_id": agents[3]["agent_id"],
                    "role": "review_and_adjudication",
                    "amount_atomic": "10000000",
                    "wallet_binding_id": bindings[3]["binding_id"],
                    "controller_commitment_hash": _controller(f"{unique_name}-3"),
                },
                {
                    "agent_id": agents[4]["agent_id"],
                    "role": "data_tools_infrastructure",
                    "amount_atomic": "5000000",
                    "wallet_binding_id": bindings[4]["binding_id"],
                    "controller_commitment_hash": _controller(f"{unique_name}-4"),
                },
            ],
        },
        headers=operator,
    )
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    assert plan["total_atomic"] == "100000000"
    reconciliation = await api_client.post(
        f"/v1/tokoin-private-pilot/settlements/{plan['settlement_plan_id']}"
        "/authorize-and-reconcile",
        headers=operator,
    )
    assert reconciliation.status_code == 201, reconciliation.text
    body = reconciliation.json()
    assert body["reconciled"] is True
    assert body["claimable_atomic"] == "100000000"
    assert body["classification"] == "PRE_PUBLIC_EARNED"
    assert body["mainnet_transactions"] == 0
    assert body["real_value_moved"] is False

    duplicate = await api_client.post(
        f"/v1/tokoin-private-pilot/settlements/{plan['settlement_plan_id']}"
        "/authorize-and-reconcile",
        headers=operator,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["tx_hash"] == body["tx_hash"]

    snapshot = await api_client.post(
        "/v1/tokoin-private-pilot/migration-snapshots/test-only", headers=operator
    )
    assert snapshot.status_code == 201, snapshot.text
    assert snapshot.json()["public_claim_enabled"] is False
    assert snapshot.json()["supply_conserved"] is True
    assert snapshot.json()["leaf_count"] >= 5

    async with session_factory()() as session:
        transfers = (
            await session.execute(
                select(TokoinDevnetTransfer).where(
                    TokoinDevnetTransfer.settlement_plan_id == plan["settlement_plan_id"]
                )
            )
        ).scalars().all()
        entitlements = (
            await session.execute(
                select(PrePublicRewardEntitlement).where(
                    PrePublicRewardEntitlement.settlement_plan_id == plan["settlement_plan_id"]
                )
            )
        ).scalars().all()
    assert len(transfers) == 1
    assert len(entitlements) == 5
    assert sum(int(row.amount_atomic) for row in entitlements) == 100000000


async def test_deterministic_100_agent_simulation(api_client):
    # The simulation endpoint is pure computation: no LLM, no real agents,
    # no public chain and no Genesis-100 activation.
    response = await api_client.get("/v1/tokoin-private-pilot/simulations/genesis-100")
    assert response.status_code == 200
    body = response.json()
    assert body["simulated_agents"] == 100
    assert body["cycles"] == 500
    assert body["successful_settlements"] == 100
    assert body["supply_conserved"] is True
    assert body["genesis_100_live_activation"] is False
