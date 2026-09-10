"""TOKOIN fixed-supply economy tests.

TOKOIN is an internal AGORA world token. These tests verify the properties
that matter for the first in-world currency: no mint API, automatic wallets,
mission-scoped rewards, append-only ledger entries and hash-chain integrity.
"""

import importlib.util
from pathlib import Path

import pytest
from agora_api.config import get_settings
from agora_api.db import session_factory
from agora_api.models import RecordProvenance, TokoinWallet
from agora_api.tokoins_service import signed_transfer_message
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


@pytest.fixture
def grant_reward_admin(monkeypatch):
    def grant(reg):
        monkeypatch.setattr(get_settings(), "tokoin_reward_admin_agent_ids", [reg["agent_id"]])

    return grant


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


async def test_public_tokoin_balances_are_aggregate_only(api_client):
    status = (await api_client.get("/v1/tokoins/status")).json()
    response = await api_client.get("/v1/tokoins/balances")
    assert response.status_code == 200, response.text
    balances = response.json()
    assert balances["balance_scope"] == "aggregate_only"
    assert balances["per_wallet_balances_exposed"] is False
    assert balances["balances"]["treasury"]["balance_aceros"] == status["treasury_balance_aceros"]
    assert (
        balances["balances"]["circulating"]["balance_aceros"] == status["circulating_supply_aceros"]
    )
    assert balances["wallet_count"] == status["wallet_count"]
    assert status["wallet_count"] == sum(status["wallet_count_by_provenance"].values())
    assert status["real_wallet_count"] == status["wallet_count_by_provenance"].get("real", 0)
    assert status["wallet_count_semantics"] == ("all_historical_rows_separate_from_real_adoption")
    assert balances["blockchain"] == status["blockchain"]


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
    async with session_factory()() as session:
        agent_provenance = await session.get(RecordProvenance, ("agents", reg["agent_id"]))
        wallet_provenance = await session.get(
            RecordProvenance, ("tokoin_wallets", reg["wallet_id"])
        )
    assert wallet_provenance.provenance_class == agent_provenance.provenance_class
    assert wallet_provenance.world_instance_id == agent_provenance.world_instance_id


async def test_wallet_provision_is_idempotent_for_existing_unwalleted_agent(
    api_client, unique_name
):
    reg = await register_agent(api_client, SigningKeypair(), unique_name)
    async with session_factory()() as session:
        wallet = (
            await session.execute(
                text("select wallet_id from tokoin_wallets where agent_id = :agent_id"),
                {"agent_id": reg["agent_id"]},
            )
        ).scalar_one()
        await session.delete(await session.get(TokoinWallet, wallet))
        await session.commit()

    first = await api_client.post("/v1/agents/me/wallet/provision", headers=_auth(reg))
    assert first.status_code == 201, first.text
    assert first.json()["created"] is True
    assert first.json()["balance_aceros"] == 0
    second = await api_client.post("/v1/agents/me/wallet/provision", headers=_auth(reg))
    assert second.status_code == 201, second.text
    assert second.json()["created"] is False
    assert second.json()["wallet_id"] == first.json()["wallet_id"]

    async with session_factory()() as session:
        count = (
            await session.execute(
                text("select count(*) from tokoin_wallets where agent_id = :agent_id"),
                {"agent_id": reg["agent_id"]},
            )
        ).scalar_one()
    assert count == 1


async def test_wallet_population_audit_is_read_only_and_reports_fixed_supply(api_client):
    audit = (await api_client.get("/v1/tokoins/wallet-audit")).json()
    assert audit["supply_conserved"] is True
    assert audit["total_balance_aceros"] == 100_000_000_000_000
    assert audit["max_supply_aceros"] == 100_000_000_000_000
    assert audit["ledger_chain"]["valid"] is True
    assert audit["duplicate_agent_wallet_groups"] == 0
    assert "by_provenance_class" in audit


async def test_tokoin_mission_reward_transfers_without_minting(
    api_client, unique_name, grant_reward_admin
):
    coordinator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-coordinator")
    worker = await register_agent(api_client, SigningKeypair(), f"{unique_name}-worker")
    grant_reward_admin(coordinator)
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

    worker_wallet = (await api_client.get(f"/v1/agents/{worker['agent_id']}/wallet")).json()
    assert worker_wallet["balance"] == 0.00000025
    assert worker_wallet["balance_aceros"] == 25
    after = (await api_client.get("/v1/tokoins/status")).json()
    assert after["treasury_balance_aceros"] == before["treasury_balance_aceros"] - 25
    assert after["circulating_supply_aceros"] == before["circulating_supply_aceros"] + 25

    ledger = (await api_client.get("/v1/tokoins/ledger")).json()
    assert ledger["verification"]["valid"] is True
    assert ledger["verification"]["total_balance"] == 100_000_000_000_000


async def test_tokoin_blockchain_seals_ledger_entries_without_economic_effect(
    api_client, unique_name, grant_reward_admin
):
    coordinator = await register_agent(
        api_client, SigningKeypair(), f"{unique_name}-block-coordinator"
    )
    worker = await register_agent(api_client, SigningKeypair(), f"{unique_name}-block-worker")
    initial_seal = await api_client.post("/v1/tokoins/blockchain/seal", headers=_auth(coordinator))
    assert initial_seal.status_code == 201, initial_seal.text
    assert initial_seal.json()["verification"]["valid"] is True

    grant_reward_admin(coordinator)
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
            "amount": 7,
            "reason": "blockchain_seal_test_reward",
        },
        headers=_auth(coordinator),
    )
    assert reward.status_code == 201, reward.text
    pending = (await api_client.get("/v1/tokoins/blockchain")).json()["verification"]
    assert pending["valid"] is True
    assert pending["pending_entries"] >= 1

    sealed = await api_client.post("/v1/tokoins/blockchain/seal", headers=_auth(worker))
    assert sealed.status_code == 201, sealed.text
    body = sealed.json()
    assert body["sealed"] is True
    assert body["economic_effect"] == "none_no_mint_no_transfer"
    assert body["verification"]["valid"] is True
    assert body["verification"]["pending_entries"] == 0
    block = body["block"]
    assert block["block_hash"]
    assert block["transaction_merkle_root"]
    assert block["proof_bundle_hash"]
    assert block["proof_bundle"]["schema"] == "agora.tokoin.block_proof_bundle.v2"
    assert any(
        entry["entry_id"] == reward.json()["entry_id"] for entry in block["proof_bundle"]["entries"]
    )

    after = (await api_client.get("/v1/tokoins/status")).json()
    assert after["treasury_balance_aceros"] == before["treasury_balance_aceros"] - 7
    assert after["circulating_supply_aceros"] == before["circulating_supply_aceros"] + 7
    assert after["blockchain"]["valid"] is True


async def test_signed_wallet_transfer_requires_device_signature_and_rejects_replay(
    api_client, unique_name, grant_reward_admin
):
    coordinator_key = SigningKeypair()
    receiver_key = SigningKeypair()
    coordinator = await register_agent(api_client, coordinator_key, f"{unique_name}-signed-sender")
    receiver = await register_agent(api_client, receiver_key, f"{unique_name}-signed-receiver")
    grant_reward_admin(coordinator)
    mission = await _create_mission(api_client, coordinator)
    mission_id = mission["mission_id"]
    joined = await api_client.post(
        f"/v1/missions/{mission_id}/join",
        json={"roles": ["researcher"]},
        headers=_auth(coordinator),
    )
    assert joined.status_code == 201
    funded = await api_client.post(
        f"/v1/missions/{mission_id}/tokoin-rewards",
        json={
            "agent_id": coordinator["agent_id"],
            "amount": 50,
            "reason": "signed_transfer_funding",
        },
        headers=_auth(coordinator),
    )
    assert funded.status_code == 201, funded.text

    receiver_wallet = (await api_client.get("/v1/agents/me/wallet", headers=_auth(receiver))).json()
    nonce = f"nonce-{unique_name}-001"
    intent = {
        "to_wallet_id": receiver_wallet["wallet_id"],
        "amount": 11,
        "reason": "signed_peer_transfer",
        "nonce": nonce,
    }
    message = (
        await api_client.post(
            "/v1/agents/me/wallet/transfer-message",
            json=intent,
            headers=_auth(coordinator),
        )
    ).json()
    assert message["context"] == "agora.tokoin.transfer.v1"
    assert message["from_wallet_id"] == coordinator["wallet_id"]
    assert (
        message["canonical_message"]
        == signed_transfer_message(
            from_wallet_id=coordinator["wallet_id"],
            to_wallet_id=receiver_wallet["wallet_id"],
            amount=11,
            reason="signed_peer_transfer",
            nonce=nonce,
        ).decode()
    )

    invalid = await api_client.post(
        "/v1/agents/me/wallet/transfers",
        json={**intent, "signature": receiver_key.sign_b64(message["canonical_message"].encode())},
        headers=_auth(coordinator),
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_failed"

    valid_signature = coordinator_key.sign_b64(message["canonical_message"].encode())
    valid = await api_client.post(
        "/v1/agents/me/wallet/transfers",
        json={**intent, "signature": valid_signature},
        headers=_auth(coordinator),
    )
    assert valid.status_code == 201, valid.text
    entry = valid.json()
    assert entry["entry_type"] == "transfer"
    assert entry["amount_aceros"] == 11

    replay = await api_client.post(
        "/v1/agents/me/wallet/transfers",
        json={**intent, "signature": valid_signature},
        headers=_auth(coordinator),
    )
    assert replay.status_code == 422
    assert "nonce" in replay.json()["error"]["message"]

    async with session_factory()() as session:
        authorization = (
            await session.execute(
                text(
                    "select authorization_type, signer_agent_id, signer_device_id "
                    "from tokoin_transaction_authorizations where entry_id = :entry_id"
                ),
                {"entry_id": entry["entry_id"]},
            )
        ).one()
        assert authorization.authorization_type == "agent_wallet_signature"
        assert authorization.signer_agent_id == coordinator["agent_id"]
        assert authorization.signer_device_id == coordinator["device_id"]

    blockchain = (await api_client.get("/v1/tokoins/blockchain")).json()["verification"]
    assert blockchain["valid"] is True
    assert blockchain["signed_transfer_entries"] >= 1


async def test_tokoin_blockchain_export_is_independently_verifiable(api_client, unique_name):
    reg = await register_agent(api_client, SigningKeypair(), f"{unique_name}-export")
    sealed = await api_client.post("/v1/tokoins/blockchain/seal", headers=_auth(reg))
    assert sealed.status_code == 201, sealed.text
    export = (await api_client.get("/v1/tokoins/blockchain/export?limit_entries=1000")).json()
    assert export["schema"] == "agora.tokoin.chain_export.v1"
    assert export["verification"]["valid"] is True
    assert export["wallets"]
    assert export["blocks"]
    total_balance = sum(wallet["balance_aceros"] for wallet in export["wallets"])
    assert total_balance == 100_000_000_000_000

    script_path = Path(__file__).parents[2] / "scripts" / "verify-tokoin-chain.py"
    spec = importlib.util.spec_from_file_location("verify_tokoin_chain", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.verify(export)
    assert result["valid"] is True
    assert result["blocks"] == export["verification"]["blocks"]
    assert result["total_balance_aceros"] == 100_000_000_000_000


async def test_tokoin_blocks_are_append_only(api_client, unique_name):
    reg = await register_agent(api_client, SigningKeypair(), f"{unique_name}-block-guard")
    sealed = await api_client.post("/v1/tokoins/blockchain/seal", headers=_auth(reg))
    assert sealed.status_code == 201, sealed.text

    async with session_factory()() as session:
        block_id = (
            await session.execute(text("select block_id from tokoin_blocks limit 1"))
        ).scalar_one_or_none()
        assert block_id is not None
        with pytest.raises(DBAPIError):
            await session.execute(
                text("UPDATE tokoin_blocks SET block_hash = block_hash WHERE block_id = :id"),
                {"id": block_id},
            )
            await session.commit()
        await session.rollback()

        with pytest.raises(DBAPIError):
            await session.execute(
                text("DELETE FROM tokoin_blocks WHERE block_id = :id"), {"id": block_id}
            )
            await session.commit()
        await session.rollback()

    blockchain = (await api_client.get("/v1/tokoins/blockchain")).json()
    assert blockchain["verification"]["valid"] is True


async def test_tokoin_rewards_are_creator_and_participant_scoped(
    api_client, unique_name, grant_reward_admin
):
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-creator")
    participant = await register_agent(api_client, SigningKeypair(), f"{unique_name}-participant")
    outsider = await register_agent(api_client, SigningKeypair(), f"{unique_name}-outsider")
    grant_reward_admin(creator)
    mission = await _create_mission(api_client, creator)
    mission_id = mission["mission_id"]
    await api_client.post(f"/v1/missions/{mission_id}/join", json={}, headers=_auth(participant))

    grant_reward_admin(participant)
    non_creator = await api_client.post(
        f"/v1/missions/{mission_id}/tokoin-rewards",
        json={"agent_id": creator["agent_id"], "amount": 1, "reason": "not_authorized"},
        headers=_auth(participant),
    )
    assert non_creator.status_code == 403

    grant_reward_admin(creator)
    not_participant = await api_client.post(
        f"/v1/missions/{mission_id}/tokoin-rewards",
        json={"agent_id": outsider["agent_id"], "amount": 1, "reason": "not_participant"},
        headers=_auth(creator),
    )
    assert not_participant.status_code == 403


async def test_tokoin_reward_payload_rejects_unknown_mint_field(
    api_client, unique_name, grant_reward_admin
):
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-creator")
    participant = await register_agent(api_client, SigningKeypair(), f"{unique_name}-participant")
    grant_reward_admin(creator)
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


async def test_ordinary_mission_creator_cannot_spend_world_treasury(
    api_client, unique_name, monkeypatch
):
    monkeypatch.setattr(get_settings(), "tokoin_reward_admin_agent_ids", [])
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-ordinary-creator")
    mission = await _create_mission(api_client, creator)
    await api_client.post(
        f"/v1/missions/{mission['mission_id']}/join", json={}, headers=_auth(creator)
    )
    before = (await api_client.get("/v1/tokoins/status")).json()["treasury_balance_aceros"]
    response = await api_client.post(
        f"/v1/missions/{mission['mission_id']}/tokoin-rewards",
        json={
            "agent_id": creator["agent_id"],
            "amount": 1_000_000_000_000,
            "reason": "unbudgeted_request",
        },
        headers=_auth(creator),
    )
    assert response.status_code == 403, response.text
    assert (await api_client.get("/v1/tokoins/status")).json()["treasury_balance_aceros"] == before


async def test_legacy_treasury_rewards_denied_in_production_even_for_operator(
    api_client, unique_name, monkeypatch, grant_reward_admin
):
    from types import SimpleNamespace

    from agora_api.routes import tokoins

    creator = await register_agent(
        api_client, SigningKeypair(), f"{unique_name}-production-operator"
    )
    grant_reward_admin(creator)
    mission = await _create_mission(api_client, creator)
    await api_client.post(
        f"/v1/missions/{mission['mission_id']}/join", json={}, headers=_auth(creator)
    )
    before = (await api_client.get("/v1/tokoins/status")).json()["treasury_balance_aceros"]
    monkeypatch.setattr(
        tokoins,
        "get_settings",
        lambda: SimpleNamespace(
            is_production=True,
            tokoin_reward_admin_agent_ids=[creator["agent_id"]],
        ),
    )
    response = await api_client.post(
        f"/v1/missions/{mission['mission_id']}/tokoin-rewards",
        json={"agent_id": creator["agent_id"], "amount": 1, "reason": "production_denied"},
        headers=_auth(creator),
    )
    assert response.status_code == 409, response.text
    assert (await api_client.get("/v1/tokoins/status")).json()["treasury_balance_aceros"] == before
