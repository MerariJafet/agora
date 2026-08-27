"""TOKOIN fixed-supply economy tests.

TOKOIN is an internal AGORA world token. These tests verify the properties
that matter for the first in-world currency: no mint API, automatic wallets,
mission-scoped rewards, append-only ledger entries and hash-chain integrity.
"""

import pytest
from agora_api.db import session_factory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _create_mission(api_client, reg: dict, *, max_participants: int = 4) -> dict:
    response = await api_client.post(
        "/v1/missions",
        json={
            "title": "TOKOIN calibration mission",
            "objective": "Verify that rewards move only from the fixed world treasury.",
            "max_participants": max_participants,
        },
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_tokoin_genesis_supply_and_chain_are_valid(api_client):
    status = (await api_client.get("/v1/tokoins/status")).json()
    assert status["currency_code"] == "TOKOIN"
    assert status["unit"] == "acero"
    assert status["aceros_per_tokoin"] == 100_000_000
    assert status["max_supply"] == 1_000_000
    assert status["max_supply_aceros"] == 100_000_000_000_000
    assert status["treasury_balance"] <= 1_000_000
    assert status["monetary_policy"] == "fixed_supply_100000000_aceros_per_tokoin_no_minting_api"

    ledger = (await api_client.get("/v1/tokoins/ledger?limit=200")).json()
    assert ledger["verification"]["valid"] is True
    assert ledger["verification"]["total_balance"] == 100_000_000_000_000
    genesis = next(row for row in ledger["ledger"] if row["sequence"] == 1)
    assert genesis["entry_type"] == "genesis"
    assert genesis["amount"] == 1_000_000
    assert genesis["amount_aceros"] == 100_000_000_000_000


async def test_registration_creates_tokoin_wallet_with_zero_balance(api_client, unique_name):
    reg = await register_agent(api_client, SigningKeypair(), unique_name)
    assert reg["_status"] == 201
    assert reg["wallet_id"].startswith("wal_")

    wallet = (await api_client.get("/v1/agents/me/wallet", headers=_auth(reg))).json()
    assert wallet["wallet_id"] == reg["wallet_id"]
    assert wallet["agent_id"] == reg["agent_id"]
    assert wallet["balance"] == 0
    assert wallet["balance_aceros"] == 0
    assert wallet["currency_code"] == "TOKOIN"


async def test_tokoin_mission_reward_transfers_without_minting(api_client, unique_name):
    coordinator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-coordinator")
    worker = await register_agent(api_client, SigningKeypair(), f"{unique_name}-worker")
    mission = await _create_mission(api_client, coordinator)
    mission_id = mission["mission_id"]
    joined = await api_client.post(
        f"/v1/missions/{mission_id}/join",
        json={"roles": ["researcher"]},
        headers=_auth(worker),
    )
    assert joined.status_code == 201

    before = (await api_client.get("/v1/tokoins/status")).json()
    reward = await api_client.post(
        f"/v1/missions/{mission_id}/tokoin-rewards",
        json={
            "agent_id": worker["agent_id"],
            "amount": 25,
            "reason": "first_world_mission_reward",
        },
        headers=_auth(coordinator),
    )
    assert reward.status_code == 201, reward.text
    entry = reward.json()
    assert entry["entry_type"] == "mission_reward"
    assert entry["amount"] == 0.00000025
    assert entry["amount_aceros"] == 25
    assert entry["mission_id"] == mission_id
    assert entry["previous_hash"]

    worker_wallet = (
        await api_client.get(f"/v1/agents/{worker['agent_id']}/wallet")
    ).json()
    assert worker_wallet["balance"] == 0.00000025
    assert worker_wallet["balance_aceros"] == 25
    after = (await api_client.get("/v1/tokoins/status")).json()
    assert after["treasury_balance_aceros"] == before["treasury_balance_aceros"] - 25
    assert after["circulating_supply_aceros"] == before["circulating_supply_aceros"] + 25

    ledger = (await api_client.get("/v1/tokoins/ledger")).json()
    assert ledger["verification"]["valid"] is True
    assert ledger["verification"]["total_balance"] == 100_000_000_000_000


async def test_tokoin_rewards_are_creator_and_participant_scoped(api_client, unique_name):
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-creator")
    participant = await register_agent(api_client, SigningKeypair(), f"{unique_name}-participant")
    outsider = await register_agent(api_client, SigningKeypair(), f"{unique_name}-outsider")
    mission = await _create_mission(api_client, creator)
    mission_id = mission["mission_id"]
    await api_client.post(f"/v1/missions/{mission_id}/join", json={}, headers=_auth(participant))

    non_creator = await api_client.post(
        f"/v1/missions/{mission_id}/tokoin-rewards",
        json={"agent_id": creator["agent_id"], "amount": 1, "reason": "not_authorized"},
        headers=_auth(participant),
    )
    assert non_creator.status_code == 403

    not_participant = await api_client.post(
        f"/v1/missions/{mission_id}/tokoin-rewards",
        json={"agent_id": outsider["agent_id"], "amount": 1, "reason": "not_participant"},
        headers=_auth(creator),
    )
    assert not_participant.status_code == 403


async def test_tokoin_reward_payload_rejects_unknown_mint_field(api_client, unique_name):
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-creator")
    participant = await register_agent(api_client, SigningKeypair(), f"{unique_name}-participant")
    mission = await _create_mission(api_client, creator)
    await api_client.post(
        f"/v1/missions/{mission['mission_id']}/join", json={}, headers=_auth(participant)
    )

    response = await api_client.post(
        f"/v1/missions/{mission['mission_id']}/tokoin-rewards",
        json={
            "agent_id": participant["agent_id"],
            "amount": 1,
            "reason": "attempted_mint",
            "mint": True,
        },
        headers=_auth(creator),
    )
    assert response.status_code == 422


async def test_tokoin_ledger_is_append_only(api_client):
    async with session_factory()() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                text("UPDATE tokoin_ledger_entries SET amount = amount WHERE sequence = 1")
            )
            await session.commit()
        await session.rollback()

        with pytest.raises(DBAPIError):
            await session.execute(text("DELETE FROM tokoin_ledger_entries WHERE sequence = 1"))
            await session.commit()
        await session.rollback()

    ledger = (await api_client.get("/v1/tokoins/ledger")).json()
    assert ledger["verification"]["valid"] is True
