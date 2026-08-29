"""MAGNA Sprint 04 TOKOIN security invariants."""

from pathlib import Path

import pytest
from agora_api.db import session_factory
from sqlalchemy import text

pytestmark = pytest.mark.security


def test_tokoin_fixed_supply_contract_has_no_mint_burn_proxy_owner_surface():
    source = Path("contracts/tokoin/contracts/TokoinFixedSupply.sol").read_text()
    assert "@openzeppelin/contracts/token/ERC20/ERC20.sol" in source
    assert "TOTAL_SUPPLY_ACEROS = 100000000000000" in source
    assert "TOKOIN_DECIMALS = 8" in source
    for forbidden in (
        "ERC20Burnable",
        "Pausable",
        "ERC20Permit",
        "ERC20Votes",
        "Ownable",
        "UUPSUpgradeable",
        "TransparentUpgradeableProxy",
        "delegatecall",
        "function mint",
        "function burn",
    ):
        assert forbidden not in source


async def test_tokoin_settlement_rejects_float_and_scientific_amounts(api_client):
    response = await api_client.post(
        "/v1/tokoin-testnet/settlement-plans",
        json={
            "reservation_id": "rsv_00000000000000000000000000",
            "resolution_receipt_id": "krr_00000000000000000000000000",
            "allocations": [
                {
                    "agent_id": "agt_00000000000000000000000000",
                    "role": "proposer",
                    "amount_atomic": "1e8",
                    "wallet_binding_id": "twb_00000000000000000000000000",
                    "controller_commitment_hash": "a" * 64,
                }
            ],
        },
    )
    assert response.status_code == 422


async def test_tokoin_status_never_reports_complete_without_ratification(api_client):
    async with session_factory()() as session:
        before = (
            await session.execute(
                text("select count(*) from events where event_type like 'tokoin.%'")
            )
        ).scalar_one()
    status = (await api_client.get("/v1/tokoin-testnet/status")).json()
    assert status["status"] == "PARTIAL_AWAITING_RATIFICATION"
    assert status["maximum_authorized_network"] == "LOCAL_DEVNET"
    assert status["human_ratifications_complete"] is False
    assert status["external_independent_audit_complete"] is False
    assert status["real_value_moved"] is False
    assert status["mainnet_transactions"] == 0
    async with session_factory()() as session:
        after = (
            await session.execute(
                text("select count(*) from events where event_type like 'tokoin.%'")
            )
        ).scalar_one()
    assert after == before
