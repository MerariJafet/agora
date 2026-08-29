"""MAGNA Sprint 04 TOKOIN security invariants."""

from pathlib import Path

import pytest
from agora_api.boundary import validate_boundary
from agora_api.db import session_factory
from agora_api.magna_tokoin_testnet import (
    ratification_bundle_view,
    release_manifest_draft_view,
    scope_matrix_view,
)
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


async def test_tokoin_status_does_not_claim_offchain_components_as_contracts(api_client):
    status = (await api_client.get("/v1/tokoin-testnet/status")).json()
    deployment = status["deployment"]
    assert set(deployment["contracts"]) == {"TokoinFixedSupply"}
    for component in (
        "GenesisTreasury",
        "RewardBudgetVault",
        "ChallengeEscrow",
        "RewardSplitter",
        "PoolEscrow",
        "AgentPassportAnchor",
        "KnowledgeRootRegistry",
        "SettlementSaga",
        "WalletBinding",
    ):
        assert component in deployment["offchain_trust_boundaries"]
    assert deployment["contract_suite"]["TokoinFixedSupply"]["upgradeability"] is False
    assert deployment["contract_suite"]["TokoinFixedSupply"]["mintability_after_genesis"] is False


def test_tokoin_scope_matrix_is_complete_and_honest():
    matrix = scope_matrix_view()
    validate_boundary("magna-tokoin-scope-matrix.schema.json", None, matrix)
    assert matrix["component_count"] == 11
    assert matrix["missing_blockers"] == []
    classifications = {item["component"]: item["classification"] for item in matrix["components"]}
    assert classifications["TokoinFixedSupply"] == "IMPLEMENTED_ONCHAIN"
    for component, classification in classifications.items():
        if component != "TokoinFixedSupply":
            assert classification in {
                "IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY",
                "INTENTIONALLY_DEFERRED_AND_NOT_IN_RELEASE",
            }
    assert classifications["PoolEscrow"] == "INTENTIONALLY_DEFERRED_AND_NOT_IN_RELEASE"


def test_tokoin_pending_ratifications_cannot_smuggle_decisions():
    bundle = ratification_bundle_view()
    validate_boundary("magna-tokoin-ratification-bundle.schema.json", None, bundle)
    assert bundle["status"] == "PENDING_HUMAN_RATIFICATION"
    assert {item["decision_id"] for item in bundle["ratifications"]} == {
        "RAT-01",
        "RAT-02",
        "RAT-03",
        "RAT-04",
        "RAT-05",
        "RAT-06",
        "RAT-07",
        "RAT-08",
    }
    for item in bundle["ratifications"]:
        assert item["status"] == "PENDING"
        assert item["decision_value"] is None
        assert item["signed_by"] is None
        assert item["signed_at"] is None
        assert item["evidence_hash"] is None


def test_tokoin_release_manifest_remains_draft_until_audit_and_ratification():
    manifest = release_manifest_draft_view()
    validate_boundary("magna-tokoin-release-manifest.schema.json", None, manifest)
    assert manifest["status"] == "DRAFT_NOT_FROZEN"
    assert manifest["maximum_authorized_network"] == "LOCAL_DEVNET"
    assert manifest["external_independent_audit_complete"] is False
    assert manifest["public_testnet_deployed"] is False
    assert manifest["mainnet_transactions"] == 0
    assert manifest["real_value_moved"] is False


async def test_tokoin_gate_get_endpoints_are_read_only(api_client):
    async with session_factory()() as session:
        before = (
            await session.execute(
                text("select count(*) from events where event_type like 'tokoin.%'")
            )
        ).scalar_one()
    for path in (
        "/v1/tokoin-testnet/scope-matrix",
        "/v1/tokoin-testnet/ratification-bundle",
        "/v1/tokoin-testnet/release-manifest",
    ):
        response = await api_client.get(path)
        assert response.status_code == 200, response.text
    async with session_factory()() as session:
        after = (
            await session.execute(
                text("select count(*) from events where event_type like 'tokoin.%'")
            )
        ).scalar_one()
    assert after == before
