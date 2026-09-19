"""A university Agent proposes; only the institution's signed decision validates."""

import hashlib

import pytest
from agora_api.db import session_factory
from agora_api.models import (
    Agent,
    InstitutionAgentDecision,
    InstitutionalReview,
    InstitutionalValidator,
    TokoinLedgerEntry,
    User,
)
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_research_protocol import _login, _register_institution
from tests.integration.test_research_protocol_institutional_validators import _freeze_candidate

pytestmark = pytest.mark.integration


def _auth(agent: dict) -> dict:
    return {"Authorization": f"Bearer {agent['session_token']}"}


def _proposal(package: dict, institution_id: str) -> dict:
    context = package["review_context"]
    total = context["reward_context"]["total_aceros"]
    return {
        "candidate_content_hash": package["candidate"]["content_hash"],
        "review": {
            "institution_id": institution_id,
            "verdict": "INSUFFICIENT_EVIDENCE",
            "methodology_review": (
                "The method was inspected against the exact candidate and declared limits."
            ),
            "evidence_review": (
                "The provided evidence and public provenance were checked independently."
            ),
            "paper_review": "The candidate text does not exceed the evidence in this test fixture.",
            "experiment_review": "No independent experiment was run for this protocol fixture.",
            "conflict_declaration": "No conflict of interest was identified.",
        },
        "recommendation": {
            "assessment": "INSUFFICIENT_EVIDENCE",
            "rationale": (
                "This protocol fixture does not contain a scientific reproduction receipt."
            ),
            "blocking_issues": ["Scientific reproduction is not documented."],
            "what_is_missing": ["An independent candidate-bound experiment receipt."],
            "suggested_actions": ["Run a method-specific replication before scientific approval."],
        },
        "evidence_manifest": {
            "context_hash": context["context_hash"],
            "participant_ids": [row["agent_id"] for row in context["participants"]],
            "thread_entry_ids": [
                *[row["entry_id"] for row in context["challenge_thread"]],
                *[row["message_id"] for row in context["world_conversation"]],
                *[row["post_id"] for row in context["forum_conversation"]],
            ],
            "event_ids": [row["event_id"] for row in context["audit_events"]],
            "artifact_ids": [package["final_solution"]["object_id"]],
            "test_receipt_hashes": [],
        },
        "tokoin_recommendation": {
            "denomination": "ACEROS",
            "total_aceros": total,
            "allocations": [
                {
                    "recipient_kind": "AGENT",
                    "recipient_id": package["submission"]["author_agent_id"],
                    "amount_aceros": total,
                    "basis": "Advisory share for the author of the frozen candidate.",
                }
            ]
            if total
            else [],
            "advisory_only": True,
            "settlement_eligible": False,
        },
    }


async def test_university_agent_requires_signed_mandate_and_owner_review(api_client, unique_name):
    candidate, creator = await _freeze_candidate(api_client, unique_name)
    reward = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reward",
        json={"total_aceros": 100_000_000},
        headers=_auth(creator),
    )
    assert reward.status_code == 201, reward.text
    async with session_factory()() as session:
        ledger_before = (
            await session.execute(select(func.count()).select_from(TokoinLedgerEntry))
        ).scalar_one()

    institution_key = SigningKeypair()
    institution, _ = await _register_institution(api_client, unique_name, institution_key)
    representative_name = f"institution-{unique_name}"
    representative_headers = await _login(api_client, representative_name)
    delegated = await register_agent(
        api_client, SigningKeypair(), f"{unique_name}-university-delegate"
    )
    outsider = await register_agent(api_client, SigningKeypair(), f"{unique_name}-outsider")
    async with session_factory()() as session:
        owner = (
            await session.execute(select(User).where(User.username == representative_name))
        ).scalar_one()
        agent = await session.get(Agent, delegated["agent_id"])
        assert agent is not None
        agent.owner_id = owner.user_id
        await session.commit()

    self_verify = await api_client.post(
        f"/v1/research-protocol/institutions/{institution['institution_id']}/verify",
        json={"verification_evidence_hash": hashlib.sha256(b"self").hexdigest()},
        headers=representative_headers,
    )
    assert self_verify.status_code == 403
    operator_headers = await _login(api_client, f"operator-{unique_name}")
    verified = await api_client.post(
        f"/v1/research-protocol/institutions/{institution['institution_id']}/verify",
        json={"verification_evidence_hash": hashlib.sha256(unique_name.encode()).hexdigest()},
        headers=operator_headers,
    )
    assert verified.status_code == 200, verified.text

    denied_prepare = await api_client.post(
        "/v1/research-protocol/institutions/me/agent-mandates",
        json={"agent_id": delegated["agent_id"]},
        headers=operator_headers,
    )
    assert denied_prepare.status_code == 404
    representative_headers = await _login(api_client, representative_name)
    prepared = await api_client.post(
        "/v1/research-protocol/institutions/me/agent-mandates",
        json={"agent_id": delegated["agent_id"]},
        headers=representative_headers,
    )
    assert prepared.status_code == 201, prepared.text
    mandate = prepared.json()
    assert mandate["state"] == "PENDING"
    assert mandate["delegation_role"] == "UNIVERSITY_AGENT"
    denied_agent_queue = await api_client.get(
        "/v1/research-protocol/institution-agent/me/queue", headers=_auth(delegated)
    )
    assert denied_agent_queue.status_code == 403
    invalid_activation = await api_client.post(
        f"/v1/research-protocol/institutions/me/agent-mandates/{mandate['mandate_id']}/activate",
        json={"signature": SigningKeypair().sign_b64(mandate["mandate_hash"].encode())},
        headers=representative_headers,
    )
    assert invalid_activation.status_code == 403
    activation = await api_client.post(
        f"/v1/research-protocol/institutions/me/agent-mandates/{mandate['mandate_id']}/activate",
        json={"signature": institution_key.sign_b64(mandate["mandate_hash"].encode())},
        headers=representative_headers,
    )
    assert activation.status_code == 200, activation.text
    assert activation.json()["signed_by_institution"] is True
    bypass = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reviews",
        json={
            "institution_id": institution["institution_id"],
            "verdict": "INSUFFICIENT_EVIDENCE",
            "methodology_review": "The delegated Agent must prepare the method assessment.",
            "evidence_review": "The delegated Agent must inspect public evidence.",
            "paper_review": "The delegated Agent must inspect the candidate manuscript.",
            "experiment_review": "Independent experiments have not been documented.",
            "conflict_declaration": "No conflict declared.",
            "signature": "A" * 86,
        },
        headers=representative_headers,
    )
    assert bypass.status_code == 403
    denied_package = await api_client.get(
        f"/v1/research-protocol/institution-agent/me/candidates/{candidate['candidate_id']}/package",
        headers=_auth(outsider),
    )
    assert denied_package.status_code == 403
    queue = await api_client.get(
        "/v1/research-protocol/institution-agent/me/queue", headers=_auth(delegated)
    )
    assert queue.status_code == 200, queue.text
    assert candidate["candidate_id"] in {row["candidate_id"] for row in queue.json()["candidates"]}
    package_response = await api_client.get(
        f"/v1/research-protocol/institution-agent/me/candidates/{candidate['candidate_id']}/package",
        headers=_auth(delegated),
    )
    assert package_response.status_code == 200, package_response.text
    package = package_response.json()
    assert package["institution_agent"]["institution_id"] == institution["institution_id"]
    assert "validator_id" not in package
    proposal_payload = _proposal(package, institution["institution_id"])
    unsupported_approval = {
        **proposal_payload,
        "review": {**proposal_payload["review"], "verdict": "APPROVED"},
        "recommendation": {
            **proposal_payload["recommendation"],
            "assessment": "PASS",
            "blocking_issues": [],
        },
    }
    denied_approval = await api_client.post(
        f"/v1/research-protocol/institution-agent/me/candidates/{candidate['candidate_id']}/proposal",
        json=unsupported_approval,
        headers=_auth(delegated),
    )
    assert denied_approval.status_code == 422
    proposed = await api_client.post(
        f"/v1/research-protocol/institution-agent/me/candidates/{candidate['candidate_id']}/proposal",
        json=proposal_payload,
        headers=_auth(delegated),
    )
    assert proposed.status_code == 201, proposed.text
    first = proposed.json()
    assert first["state"] == "AWAITING_OWNER_DECISION"
    assert first["counts_as_institutional_review"] is False
    assert first["tokoin_settlement_authorized"] is False
    premature = await api_client.post(
        f"/v1/research-protocol/institution-agent/me/proposals/{first['proposal_id']}/submit",
        headers=_auth(delegated),
    )
    assert premature.status_code == 403
    async with session_factory()() as session:
        assert (
            await session.execute(select(func.count()).select_from(InstitutionalReview))
        ).scalar_one() == 0

    stale = await api_client.post(
        f"/v1/research-protocol/institutions/me/agent-proposals/{first['proposal_id']}/decision",
        json={
            "decision": "REQUEST_REVISION",
            "proposal_hash": "0" * 64,
            "owner_notes": "The evidence needs a more precise scope statement.",
        },
        headers=representative_headers,
    )
    assert stale.status_code == 409
    revision = await api_client.post(
        f"/v1/research-protocol/institutions/me/agent-proposals/{first['proposal_id']}/decision",
        json={
            "decision": "REQUEST_REVISION",
            "proposal_hash": first["proposal_hash"],
            "owner_notes": "Clarify the scope of this bounded reproduction.",
        },
        headers=representative_headers,
    )
    assert revision.status_code == 200, revision.text
    revised = await api_client.post(
        f"/v1/research-protocol/institution-agent/me/candidates/{candidate['candidate_id']}/proposal",
        json=proposal_payload,
        headers=_auth(delegated),
    )
    assert revised.status_code == 201, revised.text
    second = revised.json()
    assert second["proposal_version"] == 2
    signing = await api_client.post(
        f"/v1/research-protocol/institutions/me/agent-proposals/{second['proposal_id']}/signing-payload",
        json={"owner_notes": "I accept this exact bounded institutional recommendation."},
        headers=representative_headers,
    )
    assert signing.status_code == 200, signing.text
    wrong_signature = await api_client.post(
        f"/v1/research-protocol/institutions/me/agent-proposals/{second['proposal_id']}/decision",
        json={
            "decision": "APPROVE",
            "proposal_hash": second["proposal_hash"],
            "owner_notes": "I accept this exact bounded institutional recommendation.",
            "institution_signature": SigningKeypair().sign_b64(
                signing.json()["signed_payload_hash"].encode()
            ),
        },
        headers=representative_headers,
    )
    assert wrong_signature.status_code == 403
    changed_notes = await api_client.post(
        f"/v1/research-protocol/institutions/me/agent-proposals/{second['proposal_id']}/decision",
        json={
            "decision": "APPROVE",
            "proposal_hash": second["proposal_hash"],
            "owner_notes": "A different note must invalidate the previously prepared signature.",
            "institution_signature": institution_key.sign_b64(
                signing.json()["signed_payload_hash"].encode()
            ),
        },
        headers=representative_headers,
    )
    assert changed_notes.status_code == 403
    approved = await api_client.post(
        f"/v1/research-protocol/institutions/me/agent-proposals/{second['proposal_id']}/decision",
        json={
            "decision": "APPROVE",
            "proposal_hash": second["proposal_hash"],
            "owner_notes": "I accept this exact bounded institutional recommendation.",
            "institution_signature": institution_key.sign_b64(
                signing.json()["signed_payload_hash"].encode()
            ),
        },
        headers=representative_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "OWNER_APPROVED"
    accepted = await api_client.post(
        f"/v1/research-protocol/institution-agent/me/proposals/{second['proposal_id']}/submit",
        headers=_auth(delegated),
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["tokoin_released"] is False
    repeated = await api_client.post(
        f"/v1/research-protocol/institution-agent/me/proposals/{second['proposal_id']}/submit",
        headers=_auth(delegated),
    )
    assert repeated.status_code == 201
    assert repeated.json()["review_id"] == accepted.json()["review_id"]
    async with session_factory()() as session:
        review = await session.get(InstitutionalReview, accepted.json()["review_id"])
        assert review is not None
        assert review.agent_proposal_id == second["proposal_id"]
        assert review.submitted_by_agent_id == delegated["agent_id"]
        assert review.institutional_notes == (
            "I accept this exact bounded institutional recommendation."
        )
        assert (
            await session.execute(
                select(func.count())
                .select_from(InstitutionalValidator)
                .where(InstitutionalValidator.actor_id == delegated["agent_id"])
            )
        ).scalar_one() == 0
        assert (
            await session.execute(select(func.count()).select_from(InstitutionAgentDecision))
        ).scalar_one() == 2
        assert (
            await session.execute(select(func.count()).select_from(TokoinLedgerEntry))
        ).scalar_one() == ledger_before
    revoked = await api_client.post(
        f"/v1/research-protocol/institutions/me/agent-mandates/{mandate['mandate_id']}/revoke",
        json={"reason": "University representative ended the delegated review pilot."},
        headers=representative_headers,
    )
    assert revoked.status_code == 200
    blocked_after_revoke = await api_client.get(
        "/v1/research-protocol/institution-agent/me/queue", headers=_auth(delegated)
    )
    assert blocked_after_revoke.status_code == 403
