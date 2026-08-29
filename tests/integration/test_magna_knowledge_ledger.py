"""MAGNA Sprint 03 Knowledge Ledger integration tests."""

import hashlib

import pytest
from agora_api.magna_knowledge_ledger import canonical_json_hash

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _agent(api_client, unique_name: str) -> dict:
    await api_client.post("/v1/world/magna/bootstrap")
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-magna-kl")


async def _object(api_client, reg: dict, payload: dict) -> dict:
    response = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json=payload,
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_canonical_hash_is_order_independent_and_domain_separated():
    left = canonical_json_hash({"b": 2, "a": 1}, domain="agora.test.left")
    right = canonical_json_hash({"a": 1, "b": 2}, domain="agora.test.left")
    other_domain = canonical_json_hash({"a": 1, "b": 2}, domain="agora.test.right")
    assert left == right
    assert left != other_domain


async def test_open_object_requires_explicit_license(api_client, unique_name):
    reg = await _agent(api_client, unique_name)
    response = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": "research_question",
            "visibility_lane": "OPEN",
            "rights_status": "unknown",
            "payload": {"question": "Can consensus become truth?"},
            "idempotency_key": f"{unique_name}-open-rights",
        },
        headers=_auth(reg),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "knowledge_ledger_violation"


async def test_sealed_object_exposes_commitment_not_plaintext(api_client, unique_name):
    reg = await _agent(api_client, unique_name)
    commitment = hashlib.sha256(b"sealed-fixture").hexdigest()
    row = await _object(
        api_client,
        reg,
        {
            "object_type": "dataset",
            "visibility_lane": "SEALED",
            "rights_status": "pending_human_review",
            "payload": {"commitment_hash": commitment, "class": "patent_candidate"},
            "idempotency_key": f"{unique_name}-sealed",
        },
    )
    assert row["payload"] is None
    assert row["public_summary"]["commitment_hash"] == commitment
    assert row["public_summary"]["plaintext_disclosed"] is False


async def test_dag_rejects_direct_cycle(api_client, unique_name):
    reg = await _agent(api_client, unique_name)
    a = await _object(
        api_client,
        reg,
        {
            "object_type": "research_question",
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {"question": "A"},
            "idempotency_key": f"{unique_name}-a",
        },
    )
    b = await _object(
        api_client,
        reg,
        {
            "object_type": "hypothesis",
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {"hypothesis": "B"},
            "idempotency_key": f"{unique_name}-b",
        },
    )
    first = await api_client.post(
        "/v1/knowledge-ledger/edges",
        json={
            "source_object_id": a["object_id"],
            "target_object_id": b["object_id"],
            "relation_type": "depends_on",
            "idempotency_key": f"{unique_name}-a-b",
        },
        headers=_auth(reg),
    )
    assert first.status_code == 201, first.text
    cycle = await api_client.post(
        "/v1/knowledge-ledger/edges",
        json={
            "source_object_id": b["object_id"],
            "target_object_id": a["object_id"],
            "relation_type": "depends_on",
            "idempotency_key": f"{unique_name}-b-a",
        },
        headers=_auth(reg),
    )
    assert cycle.status_code == 409


async def test_registered_protocol_amendment_preserves_frozen_hash(api_client, unique_name):
    reg = await _agent(api_client, unique_name)
    question = await _object(
        api_client,
        reg,
        {
            "object_type": "research_question",
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {"question": "Can negative results resolve a protocol?"},
            "idempotency_key": f"{unique_name}-question",
        },
    )
    protocol_response = await api_client.post(
        "/v1/knowledge-ledger/protocols",
        json={
            "research_question_id": question["object_id"],
            "hypothesis_ids": [],
            "confirmatory_or_exploratory": "confirmatory",
            "primary_outcomes": ["checksum matches"],
            "datasets": [],
            "methods": [{"name": "deterministic fixture"}],
            "analysis_plan": "Hash the fixture and compare it.",
            "success_criteria": ["hash matches expected output"],
            "negative_result_criteria": ["hash mismatch is informative"],
            "stopping_rules": ["one deterministic run"],
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "idempotency_key": f"{unique_name}-protocol",
        },
        headers=_auth(reg),
    )
    assert protocol_response.status_code == 201, protocol_response.text
    protocol = protocol_response.json()
    amendment = await api_client.post(
        f"/v1/knowledge-ledger/protocols/{protocol['object_id']}/amendments",
        json={
            "justification": "Document a deviation without rewriting the preregistration.",
            "changes": {"deviation": "ran on a slower CPU"},
            "idempotency_key": f"{unique_name}-amendment",
        },
        headers=_auth(reg),
    )
    assert amendment.status_code == 201, amendment.text
    amendment_payload = amendment.json()["payload"]
    assert amendment_payload["registered_protocol_frozen_hash"] == protocol["frozen_hash"]
    refetched = await api_client.get(f"/v1/knowledge-ledger/objects/{protocol['object_id']}")
    assert refetched.json()["frozen_hash"] == protocol["frozen_hash"]


async def test_reproducibility_capsule_fixture_and_receipt_do_not_pay(api_client, unique_name):
    reg = await _agent(api_client, unique_name)
    expected = hashlib.sha256(b"fixture").hexdigest()
    capsule = await _object(
        api_client,
        reg,
        {
            "object_type": "reproducibility_capsule",
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "Apache-2.0",
            "payload": {"fixture_input": "fixture", "expected_output_hash": expected},
            "idempotency_key": f"{unique_name}-capsule",
        },
    )
    verified = await api_client.post(
        f"/v1/knowledge-ledger/capsules/{capsule['object_id']}/verify",
        headers=_auth(reg),
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verified"] is True

    protocol = await _object(
        api_client,
        reg,
        {
            "object_type": "registered_protocol",
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "Apache-2.0",
            "payload": {"protocol_kind": "exploratory", "frozen": True},
            "idempotency_key": f"{unique_name}-receipt-protocol",
        },
    )
    outcome = await _object(
        api_client,
        reg,
        {
            "object_type": "outcome",
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "Apache-2.0",
            "payload": {"outcome": "negative result still informative"},
            "idempotency_key": f"{unique_name}-outcome",
        },
    )
    receipt = await api_client.post(
        "/v1/knowledge-ledger/resolution-receipts",
        json={
            "challenge_id": "chg_00000000000000000000000000",
            "outcome_id": outcome["object_id"],
            "registered_protocol_id": protocol["object_id"],
            "requested_state": "INCONCLUSIVE",
            "evidence_object_ids": [capsule["object_id"]],
            "idempotency_key": f"{unique_name}-receipt",
        },
        headers=_auth(reg),
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["decision"] == "accepted"
    assert receipt.json()["payment_eligible"] is False


async def test_merkle_batch_is_simulated_anchor_over_contiguous_objects(api_client, unique_name):
    reg = await _agent(api_client, unique_name)
    for idx in range(3):
        await _object(
            api_client,
            reg,
            {
                "object_type": "evidence",
                "visibility_lane": "OPEN",
                "rights_status": "explicit_open_license",
                "license_id": "CC-BY-4.0",
                "payload": {"title": f"Merkle fixture {idx}"},
                "idempotency_key": f"{unique_name}-merkle-{idx}",
            },
        )
    response = await api_client.post(
        "/v1/knowledge-ledger/merkle-batches",
        json={"first_sequence": 1, "last_sequence": 3},
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["leaf_count"] == 3
    assert body["merkle_root"]
    assert body["simulated_anchor_only"] is True
