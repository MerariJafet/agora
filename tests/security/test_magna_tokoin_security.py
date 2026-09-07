"""MAGNA Sprint 04 TOKOIN security invariants."""

from pathlib import Path

import agora_api.magna_tokoin_testnet as tokoin
import pytest
from agora_api.boundary import validate_boundary
from agora_api.db import session_factory
from agora_api.magna_tokoin_testnet import (
    public_testnet_readiness_view,
    ratification_bundle_view,
    release_manifest_draft_view,
    require_local_control_plane,
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
    login = await api_client.post(
        "/v1/auth/dev/login", json={"username": "tokoin-security-operator"}
    )
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
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/v1/tokoin-testnet/deployment/local-devnet",
        "/v1/tokoin-testnet/reservations",
        "/v1/tokoin-testnet/reservations/rsv_missing/confirm-local",
        "/v1/tokoin-testnet/settlement-plans",
        "/v1/tokoin-testnet/knowledge-roots",
        "/v1/tokoin-private-pilot/ratifications/ingest",
        "/v1/tokoin-private-pilot/settlements/tsp_missing/authorize-and-reconcile",
        "/v1/tokoin-private-pilot/migration-snapshots/test-only",
    ],
)
async def test_tokoin_control_plane_mutations_require_owner_csrf(api_client, path):
    response = await api_client.post(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


async def test_tokoin_control_plane_rejects_missing_csrf(api_client):
    login = await api_client.post(
        "/v1/auth/dev/login", json={"username": "tokoin-csrf-operator"}
    )
    assert login.status_code == 200
    response = await api_client.post("/v1/tokoin-testnet/deployment/local-devnet")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_rejected"


def test_tokoin_local_control_plane_fails_closed_in_production(monkeypatch):
    from agora_api.config import get_settings
    from agora_api.errors import Conflict

    get_settings.cache_clear()
    monkeypatch.setenv("AGORA_ENV", "production")
    monkeypatch.setenv("AGORA_TOKOIN_LOCAL_CONTROL_PLANE_ENABLED", "true")
    try:
        with pytest.raises(Conflict):
            require_local_control_plane()
    finally:
        get_settings.cache_clear()


def test_tokoin_local_control_plane_requires_explicit_enablement(monkeypatch):
    from agora_api.config import get_settings
    from agora_api.errors import Conflict

    get_settings.cache_clear()
    monkeypatch.setenv("AGORA_ENV", "development")
    monkeypatch.setenv("AGORA_TOKOIN_LOCAL_CONTROL_PLANE_ENABLED", "false")
    try:
        with pytest.raises(Conflict):
            require_local_control_plane()
    finally:
        get_settings.cache_clear()


async def test_tokoin_deployment_guard_rejects_unknown_fields(api_client):
    login = await api_client.post(
        "/v1/auth/dev/login", json={"username": "tokoin-guard-boundary"}
    )
    response = await api_client.post(
        "/v1/tokoin-testnet/deployment/guard",
        json={"chain_id": 31337, "mainnet_authorized": True},
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert response.status_code == 422


async def test_tokoin_status_never_reports_complete_without_external_audit(api_client):
    async with session_factory()() as session:
        before = (
            await session.execute(
                text("select count(*) from events where event_type like 'tokoin.%'")
            )
        ).scalar_one()
    status = (await api_client.get("/v1/tokoin-testnet/status")).json()
    assert status["status"] == "BLOCKED_EXTERNAL_AUDIT"
    assert status["maximum_authorized_network"] == "LOCAL_DEVNET"
    assert status["human_ratifications_complete"] is True
    assert status["external_independent_audit_complete"] is False
    assert status["real_value_moved"] is False
    assert status["mainnet_transactions"] == 0
    assert status["ratification_gate"]["pending_decisions"] == 0
    assert status["public_testnet"]["candidate_bundle"]["integrity_valid"] is True
    assert status["public_testnet"]["base_sepolia_deployed"] is False
    assert status["public_testnet"]["market_ready"] is False
    async with session_factory()() as session:
        after = (
            await session.execute(
                text("select count(*) from events where event_type like 'tokoin.%'")
            )
        ).scalar_one()
    assert after == before


def test_public_testnet_readiness_is_truthful_and_hash_bound(monkeypatch, tmp_path):
    current = public_testnet_readiness_view()
    assert current["stage"] == "AUDIT_CANDIDATE"
    assert current["candidate_bundle"]["integrity_valid"] is True
    assert "independent_external_audit_incomplete" in current["predeployment_blockers"]

    tampered = tmp_path / "bundle.json"
    bundle = tokoin._load_json_object(tokoin.CONTRACT_RELEASE_BUNDLE_PATH)
    assert bundle is not None
    bundle["target"]["mainnet_authorized"] = True
    tampered.write_text(__import__("json").dumps(bundle))
    monkeypatch.setattr(tokoin, "CONTRACT_RELEASE_BUNDLE_PATH", tampered)
    assert public_testnet_readiness_view()["candidate_bundle"]["integrity_valid"] is False


def test_public_readiness_rejects_audit_for_a_different_candidate(monkeypatch, tmp_path):
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        __import__("json").dumps(
            {
                "status": "COMPLETE_PASSED",
                "accepted_by_operator": True,
                "critical_findings": 0,
                "high_findings": 0,
                "report_hash": "a" * 64,
                "contract_release_bundle_hash": "b" * 64,
            }
        )
    )
    monkeypatch.setattr(tokoin, "EXTERNAL_AUDIT_REFERENCE_PATH", audit_path)
    result = public_testnet_readiness_view()
    assert result["candidate_bundle"]["integrity_valid"] is True
    assert result["independent_audit"]["complete"] is False
    assert "independent_external_audit_incomplete" in result["predeployment_blockers"]


def test_public_readiness_requires_independence_disclosure(monkeypatch, tmp_path):
    bundle = tokoin._load_json_object(tokoin.CONTRACT_RELEASE_BUNDLE_PATH)
    assert bundle is not None
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        __import__("json").dumps(
            {
                "status": "COMPLETE_PASSED",
                "accepted_by_operator": True,
                "critical_findings": 0,
                "high_findings": 0,
                "report_hash": "a" * 64,
                "contract_release_bundle_hash": bundle["bundle_sha256"],
            }
        )
    )
    independence_path = tmp_path / "independence.json"
    independence_path.write_text(
        __import__("json").dumps(
            {
                "status": "NOT_ENGAGED",
                "auditor": None,
                "relationship_disclosure": None,
                "accepted_by_operator": False,
            }
        )
    )
    monkeypatch.setattr(tokoin, "EXTERNAL_AUDIT_REFERENCE_PATH", audit_path)
    monkeypatch.setattr(tokoin, "AUDITOR_INDEPENDENCE_PATH", independence_path)
    result = public_testnet_readiness_view()
    assert result["independent_audit"]["complete"] is False
    assert "auditor_independence_not_confirmed" in result["predeployment_blockers"]


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


def test_tokoin_ratified_bundle_is_canonical_and_hash_bound():
    bundle = ratification_bundle_view()
    validate_boundary("magna-tokoin-ratification-bundle.schema.json", None, bundle)
    assert bundle["status"] == "COMPLETE"
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
        assert item["status"] == "RATIFIED"
        assert item["decision_value"]["source_hash"] == (
            "2bee72496f3c9ddb94a2e3a7cd041df04b205b784acc2110304ab2347dd20088"
        )
        assert item["signed_by"] == "Merari Acero"
        assert item["signed_at"] == "2026-08-29T15:22:32Z"
        assert item["evidence_hash"] == (
            "2bee72496f3c9ddb94a2e3a7cd041df04b205b784acc2110304ab2347dd20088"
        )


def test_tokoin_missing_ratification_bundle_falls_back_to_pending(monkeypatch, tmp_path):
    monkeypatch.setattr(tokoin, "RATIFIED_FOUNDER_BUNDLE_PATH", tmp_path / "missing.json")
    bundle = tokoin.ratification_bundle_view()
    validate_boundary("magna-tokoin-ratification-bundle.schema.json", None, bundle)
    assert bundle["status"] == "PENDING_HUMAN_RATIFICATION"
    for item in bundle["ratifications"]:
        assert item["status"] == "PENDING"
        assert item["decision_value"] is None


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
