"""Security and workflow gates for synthetic Institutional Validators."""

import hashlib

import pytest
from agora_api.db import session_factory
from agora_api.institutional_validator_service import review_commitment
from agora_api.models import (
    Agent,
    Event,
    InstitutionalValidator,
    MagnaKnowledgeObject,
    ResearchCandidateSnapshot,
    TokoinLedgerEntry,
    User,
    ValidatorAssignment,
)
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_research_protocol import _join, _login, _seed_challenge

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _freeze_candidate(api_client, unique_name: str) -> tuple[dict, dict]:
    await api_client.post("/v1/world/magna/bootstrap")
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-author")
    peers = [
        await register_agent(api_client, SigningKeypair(), f"{unique_name}-peer-{index}")
        for index in range(2)
    ]
    mission_id = await _seed_challenge(api_client, unique_name, creator)
    for reg in (creator, *peers):
        await _join(api_client, mission_id, reg)
    submission = await api_client.post(
        f"/v1/mission-challenges/{mission_id}/submissions",
        json={
            "idempotency_key": f"{unique_name}-submission",
            "solution_summary": "A falsifiable candidate for blind institutional protocol testing.",
            "claim_ids": [],
            "artifact_version_ids": [],
            "evidence_ids": [],
            "limitations": "Synthetic validators do not constitute human scientific validation.",
            "public_rationale": (
                "The candidate exists only to exercise independent review controls."
            ),
            "reasoning_outline": (
                "Freeze exact bytes, commit independently, then reveal both reviews."
            ),
            "experiments": {"fixture": "deterministic", "expected": "dual_blind_review"},
            "methodology": {
                "hypothesis": "Peer drafts remain sealed through the commitment phase.",
                "novelty_check": "Protocol security fixture only.",
                "method_type": "computational_experiment",
                "verification_plan": (
                    "Inspect API projections and immutable event/genealogy records."
                ),
                "falsifiability": "Any early verdict disclosure falsifies the claim.",
                "reproducibility": "Run this test from an empty isolated database.",
                "evidence_standard": "replicable_computation",
                "limitations": "No real university or human scientific attestation.",
            },
        },
        headers=_auth(creator),
    )
    assert submission.status_code == 201, submission.text
    submission_id = submission.json()["submission_id"]
    solution = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": "candidate_solution",
            "challenge_id": mission_id,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {"claim": "The blind-review protocol enforces independent commitments."},
            "idempotency_key": f"{unique_name}-solution",
        },
        headers=_auth(creator),
    )
    assert solution.status_code == 201, solution.text
    for index, peer in enumerate(peers):
        vote = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/votes",
            json={
                "verdict": "resolved",
                "public_rationale": "Sufficient to nominate a test candidate, not establish truth.",
                "idempotency_key": f"{unique_name}-vote-{index}",
                "review_evidence_ids": [],
                "conflict_of_interest_declaration": "No known conflict in this isolated fixture.",
            },
            headers=_auth(peer),
        )
        assert vote.status_code == 200, vote.text
    candidate = await api_client.post(
        f"/v1/research-protocol/challenges/{mission_id}/candidates",
        json={
            "submission_id": submission_id,
            "final_solution_object_id": solution.json()["object_id"],
            "idempotency_key": f"{unique_name}-candidate",
        },
        headers=_auth(creator),
    )
    assert candidate.status_code == 201, candidate.text
    return candidate.json(), creator


def _review_payload(nonce: str, *, verdict: str, reproduction_status: str) -> dict:
    score = 4 if reproduction_status == "REPRODUCED" else 2
    text = "Independent test execution inspected the exact frozen candidate and its evidence."
    return {
        "commitment_nonce": nonce,
        "verdict": verdict,
        "confidence": 82,
        "reproduction_status": reproduction_status,
        "dimensions": {
            "question_validity": 4,
            "methodology": 4,
            "evidence": 3,
            "reproducibility": score,
            "falsifiability": 4,
            "statistics": 3,
            "code_integrity": 4,
            "data_integrity": 4,
            "literature_alignment": 3,
            "claim_scope": 4,
        },
        "summary": text,
        "methodology_findings": text,
        "reproduction_findings": text,
        "evidence_findings": text,
        "critical_issues": [] if verdict == "APPROVED" else ["Independent reproduction failed."],
        "minor_issues": [],
        "requested_changes": [] if verdict == "APPROVED" else ["Provide a reproducible capsule."],
        "executed_tests": ["deterministic fixture replay"],
        "artifacts_reviewed": [],
    }


async def test_dual_blind_pilot_is_sealed_and_cannot_release_tokoin(api_client, unique_name):
    candidate, creator = await _freeze_candidate(api_client, unique_name)
    async with session_factory()() as session:
        transfers_before = (
            await session.execute(select(func.count()).select_from(TokoinLedgerEntry))
        ).scalar_one()
    reward = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reward",
        json={"total_aceros": 100_000_000},
        headers=_auth(creator),
    )
    assert reward.status_code == 201
    validator_keys = [SigningKeypair(), SigningKeypair()]
    validators = [
        await register_agent(api_client, validator_keys[0], f"{unique_name}-validator-codex"),
        await register_agent(api_client, validator_keys[1], f"{unique_name}-validator-claude"),
    ]
    representative_headers = []
    for index, reg in enumerate(validators):
        username = f"validator-owner-{unique_name}-{index}"
        representative_headers.append(await _login(api_client, username))
        async with session_factory()() as session:
            owner = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one()
            agent = await session.get(Agent, reg["agent_id"])
            assert agent is not None
            agent.owner_id = owner.user_id
            await session.commit()

    profiles = []
    profile_specs = [
        ("codex", "REPRODUCTION_METHODOLOGY", "Universidad Codex SIMULADA"),
        ("claude", "FALSIFICATION_EVIDENCE", "Universidad Claude SIMULADA"),
    ]
    for index, (provider, role, name) in enumerate(profile_specs):
        response = await api_client.post(
            "/v1/research-protocol/institutional-validators",
            json={
                "display_name": f"Validator {'A' if index == 0 else 'B'}",
                "institution_name": name,
                "institution_type": "synthetic_university_lab",
                "legal_entity_id": f"TEST-LEGAL-{unique_name.upper()}-{index}",
                "domain": f"validator-{index}-{unique_name.lower()}.example.org",
                "jurisdiction": "TEST",
                "institution_mode": "simulated_test",
                "accreditation_status": "NOT_REAL",
                "public_label": "Institución simulada para pruebas de AGORA",
                "brain_provider": provider,
                "review_role": role,
                "scientific_domains": ["scientific-method", "reproducibility"],
            },
            headers=_auth(validators[index]),
        )
        assert response.status_code == 201, response.text
        assert response.json()["active_status"] is False
        assert response.json()["badge"] == "TEST INSTITUTIONAL VALIDATOR"
        assert response.json()["can_satisfy_human_validation"] is False
        profiles.append(response.json())

    self_activation = await api_client.post(
        f"/v1/research-protocol/institutional-validators/{profiles[0]['validator_id']}/activate",
        json={"verification_evidence_hash": hashlib.sha256(b"self").hexdigest()},
        headers=representative_headers[0],
    )
    assert self_activation.status_code == 403
    operator_headers = await _login(api_client, f"validator-operator-{unique_name}")
    for index, profile in enumerate(profiles):
        activated = await api_client.post(
            f"/v1/research-protocol/institutional-validators/{profile['validator_id']}/activate",
            json={
                "verification_evidence_hash": hashlib.sha256(
                    f"pilot-activation-{index}".encode()
                ).hexdigest()
            },
            headers=operator_headers,
        )
        assert activated.status_code == 200, activated.text

    panel_response = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/pilot-panel",
        json={"validator_ids": [profile["validator_id"] for profile in profiles]},
        headers=operator_headers,
    )
    assert panel_response.status_code == 201, panel_response.text
    panel = panel_response.json()
    assert len(panel["tracks"]) == 2
    assignments = {
        track["validator"]["actor_id"]: track["assignment_id"] for track in panel["tracks"]
    }

    package = await api_client.get(
        f"/v1/research-protocol/pilot-assignments/{assignments[validators[0]['agent_id']]}/package",
        headers=_auth(validators[0]),
    )
    assert package.status_code == 200, package.text
    assert package.json()["candidate"]["content_hash"] == candidate["content_hash"]
    assert package.json()["peer_review_data_disclosed"] is False

    payloads = [
        _review_payload(
            "nonce-codex-review-0001",
            verdict="APPROVED",
            reproduction_status="REPRODUCED",
        ),
        _review_payload(
            "nonce-claude-review-0002",
            verdict="REQUIRES_REVISION",
            reproduction_status="FAILED_TO_REPRODUCE",
        ),
    ]
    hashes = []
    async with session_factory()() as session:
        for index, reg in enumerate(validators):
            assignment = await session.get(ValidatorAssignment, assignments[reg["agent_id"]])
            profile = await session.get(InstitutionalValidator, profiles[index]["validator_id"])
            snapshot = await session.get(ResearchCandidateSnapshot, candidate["candidate_id"])
            assert assignment is not None and profile is not None and snapshot is not None
            hashes.append(review_commitment(assignment, profile, snapshot, payloads[index]))

    outsider = await register_agent(api_client, SigningKeypair(), f"{unique_name}-outsider")
    denied_package = await api_client.get(
        f"/v1/research-protocol/pilot-assignments/{assignments[validators[0]['agent_id']]}/package",
        headers=_auth(outsider),
    )
    assert denied_package.status_code == 403
    impersonation = await api_client.post(
        f"/v1/research-protocol/pilot-assignments/{assignments[validators[0]['agent_id']]}/commit",
        json={
            "commitment_hash": hashes[0],
            "commitment_signature": validator_keys[0].sign_b64(hashes[0].encode("ascii")),
            "conflict_declaration": "No conflict declared.",
        },
        headers=_auth(outsider),
    )
    assert impersonation.status_code == 403

    for index, reg in enumerate(validators):
        committed = await api_client.post(
            f"/v1/research-protocol/pilot-assignments/{assignments[reg['agent_id']]}/commit",
            json={
                "commitment_hash": hashes[index],
                "commitment_signature": validator_keys[index].sign_b64(
                    hashes[index].encode("ascii")
                ),
                "conflict_declaration": "No conflict declared for this synthetic test review.",
            },
            headers=_auth(reg),
        )
        assert committed.status_code == 200, committed.text
        assert committed.json()["draft_disclosed"] is False

    first = await api_client.post(
        f"/v1/research-protocol/pilot-assignments/{assignments[validators[0]['agent_id']]}/reveal",
        json=payloads[0],
        headers=_auth(validators[0]),
    )
    assert first.status_code == 201, first.text
    assert first.json()["verdicts_visible"] is False
    sealed = (
        await api_client.get(
            f"/v1/research-protocol/candidates/{candidate['candidate_id']}/pilot-panel"
        )
    ).json()
    assert sealed["all_revealed"] is False
    assert all("review" not in track for track in sealed["tracks"])

    second = await api_client.post(
        f"/v1/research-protocol/pilot-assignments/{assignments[validators[1]['agent_id']]}/reveal",
        json=payloads[1],
        headers=_auth(validators[1]),
    )
    assert second.status_code == 201, second.text
    assert second.json()["verdicts_visible"] is True
    assert second.json()["panel_status"] == "RETURN_TO_RESEARCH"
    revealed = (
        await api_client.get(
            f"/v1/research-protocol/candidates/{candidate['candidate_id']}/pilot-panel"
        )
    ).json()
    assert {track["review"]["verdict"] for track in revealed["tracks"]} == {
        "APPROVED",
        "REQUIRES_REVISION",
    }
    assert revealed["tokoin_settlement_eligible"] is False
    assert revealed["pilot_credit_is_non_settleable"] is True

    async with session_factory()() as session:
        snapshot = await session.get(ResearchCandidateSnapshot, candidate["candidate_id"])
        assert snapshot is not None
        challenge_id = snapshot.challenge_id
        failed_nodes = (
            await session.execute(
                select(func.count())
                .select_from(MagnaKnowledgeObject)
                .where(
                    MagnaKnowledgeObject.challenge_id == challenge_id,
                    MagnaKnowledgeObject.object_type == "reproduction_result",
                    MagnaKnowledgeObject.state == "REFUTED",
                )
            )
        ).scalar_one()
        transfers = (
            await session.execute(select(func.count()).select_from(TokoinLedgerEntry))
        ).scalar_one()
        event_types = set(
            (
                await session.execute(
                    select(Event.event_type).where(Event.event_type.like("institution.%"))
                )
            ).scalars()
        )
    assert failed_nodes == 1
    assert transfers == transfers_before
    assert {
        "institution.review.started",
        "institution.reproduction.started",
        "institution.review.finding_created",
        "institution.reproduction.completed",
        "institution.validation.conflict_detected",
    } <= event_types
    challenge_view = (
        await api_client.get(f"/v1/research-protocol/challenges/{challenge_id}")
    ).json()
    layer = challenge_view["institutional_validator_layer"]
    assert layer["pilot_can_satisfy_human_validation"] is False
    assert layer["panels"][0]["status"] == "RETURN_TO_RESEARCH"

    lock = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/lock-reward",
        headers=operator_headers,
    )
    assert lock.status_code == 409


def test_panel_result_mapping_after_dual_reveal():
    from agora_api.errors import ValidationFailed
    from agora_api.institutional_validator_service import (
        _panel_result,
        _validate_review_consistency,
    )

    assert _panel_result({"APPROVED"}) == "AGORA_PROTOCOL_VALIDATED_TEST"
    assert _panel_result({"APPROVED", "REQUIRES_REVISION"}) == "RETURN_TO_RESEARCH"
    assert _panel_result({"REJECTED"}) == "CANDIDATE_REJECTED"
    assert _panel_result({"INSUFFICIENT_EVIDENCE", "APPROVED"}) == "EVIDENCE_REVIEW_REQUIRED"

    validator = InstitutionalValidator(review_role="REPRODUCTION_METHODOLOGY")
    inconsistent = _review_payload(
        "nonce-inconsistent-review",
        verdict="APPROVED",
        reproduction_status="FAILED_TO_REPRODUCE",
    )
    with pytest.raises(ValidationFailed):
        _validate_review_consistency(validator, inconsistent)
