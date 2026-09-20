"""End-to-end gates for Research Protocol v1."""

import hashlib
from datetime import timedelta

import pytest
from agora_api.artifact_store import get_artifact_store
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.ids import new_mission_id, new_space_id
from agora_api.magna_knowledge_ledger import canonical_json_hash
from agora_api.models import Mission, Space, TokoinLedgerEntry
from agora_api.provenance import add_provenance
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _seed_challenge(api_client, unique_name: str, creator: dict) -> str:
    mission_id = new_mission_id()
    space_id = new_space_id()
    async with session_factory()() as session:
        session.add(
            Space(
                space_id=space_id,
                slug=f"research-protocol-{unique_name.lower()}",
                name="Research Protocol Test Lab",
                kind="mission_challenge",
                description="Isolated protocol test.",
                evidence_policy="optional",
                created_at=now_utc(),
            )
        )
        await session.flush()
        await add_provenance(
            session,
            record_table="spaces",
            record_id=space_id,
            created_by="test.research_protocol",
            source_reference=unique_name,
        )
        session.add(
            Mission(
                mission_id=mission_id,
                title="Falsifiable bounded protocol fixture",
                objective="Prove the institutional gate without asserting scientific truth.",
                description="A deterministic integration fixture.",
                state="active",
                visibility="public",
                hosting_space_id=space_id,
                related_claim_ids=[],
                deadline_at=now_utc() + timedelta(days=1),
                reward_aceros=100_000_000,
                challenge_kind="research_consensus_test",
                challenge_problem={"status": "open_problem", "unsolved_required": True},
                challenge_space_color="#35d0ff",
                resolution_policy="institutional_research_v1",
                max_participants=10,
                completion_policy={"institutional_quorum": 2},
                created_by_agent_id=creator["agent_id"],
                created_by_agent_version_id=creator["agent_version_id"],
                created_at=now_utc(),
                activated_at=now_utc(),
            )
        )
        await session.flush()
        await add_provenance(
            session,
            record_table="missions",
            record_id=mission_id,
            created_by="test.research_protocol",
            source_reference=unique_name,
        )
        await session.commit()
    return mission_id


async def _join(api_client, mission_id: str, reg: dict) -> None:
    response = await api_client.post(
        f"/v1/mission-challenges/{mission_id}/join", headers=_auth(reg)
    )
    assert response.status_code == 201, response.text


async def _login(api_client, username: str) -> dict:
    response = await api_client.post("/v1/auth/dev/login", json={"username": username})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


async def _register_institution(api_client, label: str, key: SigningKeypair) -> tuple[dict, str]:
    headers = await _login(api_client, f"institution-{label}")
    credential_hash = hashlib.sha256(f"credential:{label}".encode()).hexdigest()
    response = await api_client.post(
        "/v1/research-protocol/institutions",
        json={
            "legal_entity_id": f"TEST-LEGAL-{label}",
            "name": f"Test Research Institute {label}",
            "domain": f"{label}.example.org",
            "jurisdiction": "TEST",
            "signing_public_key": key.public_key_b64,
            "credential_reference": f"test://credential/{label}",
            "credential_hash": credential_hash,
            "conflict_metadata": {"test_fixture": True},
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json(), headers["X-CSRF-Token"]


async def test_consensus_cannot_pay_without_two_signed_independent_reviews(api_client, unique_name):
    await api_client.post("/v1/world/magna/bootstrap")
    creator_key = SigningKeypair()
    creator = await register_agent(api_client, creator_key, f"{unique_name}-author")
    reviewer_a = await register_agent(api_client, SigningKeypair(), f"{unique_name}-peer-a")
    reviewer_b = await register_agent(api_client, SigningKeypair(), f"{unique_name}-peer-b")
    mission_id = await _seed_challenge(api_client, unique_name, creator)
    for reg in (creator, reviewer_a, reviewer_b):
        await _join(api_client, mission_id, reg)

    artifact = (await api_client.post(
        "/v1/artifacts", json={"title": "Original research bytes", "artifact_type": "analysis"},
        headers=_auth(creator),
    )).json()
    version_response = await api_client.post(
        f"/v1/artifacts/{artifact['artifact_id']}/versions",
        files={"file": ("proof.txt", b"original evidence", "text/plain")},
        data={"metadata": "{}"}, headers=_auth(creator),
    )
    assert version_response.status_code == 201, version_response.text
    version = version_response.json()
    digest = version["content_hash"]
    blob = get_artifact_store().root / f"sha256/{digest[:2]}/{digest}"

    submission_response = await api_client.post(
        f"/v1/mission-challenges/{mission_id}/submissions",
        json={
            "idempotency_key": f"{unique_name}-submission",
            "solution_summary": "A candidate with a falsifiable bounded argument.",
            "claim_ids": [],
            "artifact_version_ids": [version["artifact_version_id"]],
            "evidence_ids": [],
            "limitations": "This fixture validates workflow, not scientific truth.",
            "public_rationale": "Independent peers can reproduce the deterministic path.",
            "reasoning_outline": "Publish, reproduce, criticize, then freeze a candidate.",
            "experiments": {
                "checked_gate": "institutional_quorum",
                "expected": "blocked_before_two_independent_reviews",
            },
            "methodology": {
                "hypothesis": "The gate blocks agent-only payout.",
                "novelty_check": "Test-only protocol scenario.",
                "method_type": "computational_experiment",
                "verification_plan": "Inspect immutable hashes and signed reviews.",
                "falsifiability": "Any pre-quorum reward release falsifies the claim.",
                "reproducibility": "Run this integration test from an empty database.",
                "evidence_standard": "replicable_computation",
                "limitations": "No external institution is represented.",
            },
        },
        headers=_auth(creator),
    )
    assert submission_response.status_code == 201, submission_response.text
    submission_id = submission_response.json()["submission_id"]
    object_response = await api_client.post(
        "/v1/knowledge-ledger/objects",
        json={
            "object_type": "candidate_solution",
            "challenge_id": mission_id,
            "visibility_lane": "OPEN",
            "rights_status": "explicit_open_license",
            "license_id": "CC-BY-4.0",
            "payload": {"claim": "The institutional gate is enforced."},
            "idempotency_key": f"{unique_name}-candidate-object",
        },
        headers=_auth(creator),
    )
    assert object_response.status_code == 201, object_response.text
    object_id = object_response.json()["object_id"]
    for index, reviewer in enumerate((reviewer_a, reviewer_b)):
        vote = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/votes",
            json={
                "verdict": "resolved",
                "public_rationale": (
                    "The bounded evidence is sufficient to nominate, not validate, the candidate."
                ),
                "idempotency_key": f"{unique_name}-vote-{index}",
                "review_evidence_ids": [],
                "conflict_of_interest_declaration": "No known conflict in this test fixture.",
            },
            headers=_auth(reviewer),
        )
        assert vote.status_code == 200, vote.text

    async with session_factory()() as session:
        transfers_before = (
            await session.execute(select(func.count()).select_from(TokoinLedgerEntry))
        ).scalar_one()
        mission = await session.get(Mission, mission_id)
        assert mission is not None and mission.state == "review"
        assert mission.winning_submission_id is None

    blob.unlink()
    blocked_candidate = await api_client.post(
        f"/v1/research-protocol/challenges/{mission_id}/candidates",
        json={"submission_id": submission_id, "final_solution_object_id": object_id,
              "idempotency_key": f"{unique_name}-missing-candidate"},
        headers=_auth(creator),
    )
    assert blocked_candidate.status_code == 409
    assert "evidence unavailable" in blocked_candidate.text
    blob.write_bytes(b"original evidence")
    candidate_response = await api_client.post(
        f"/v1/research-protocol/challenges/{mission_id}/candidates",
        json={
            "submission_id": submission_id,
            "final_solution_object_id": object_id,
            "idempotency_key": f"{unique_name}-candidate",
        },
        headers=_auth(creator),
    )
    assert candidate_response.status_code == 201, candidate_response.text
    candidate = candidate_response.json()
    candidate_retry = await api_client.post(
        f"/v1/research-protocol/challenges/{mission_id}/candidates",
        json={
            "submission_id": submission_id,
            "final_solution_object_id": object_id,
            "idempotency_key": f"{unique_name}-candidate",
        },
        headers=_auth(creator),
    )
    assert candidate_retry.status_code == 201
    assert candidate_retry.json()["candidate_id"] == candidate["candidate_id"]
    reward_url = f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reward"
    denied_reward = await api_client.post(reward_url, json={"total_aceros": 100},
                                         headers=_auth(reviewer_a))
    assert denied_reward.status_code == 403
    for invalid_amount in (0, 101, 1_000_000_000_100):
        invalid = await api_client.post(reward_url, json={"total_aceros": invalid_amount},
                                        headers=_auth(creator))
        assert invalid.status_code == 422
    reward_response = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reward",
        json={"total_aceros": 100_000_000},
        headers=_auth(creator),
    )
    assert reward_response.status_code == 201, reward_response.text
    assert reward_response.json()["state"] == "PROVISIONAL"
    retry_reward = await api_client.post(reward_url, json={"total_aceros": 100_000_000},
                                         headers=_auth(creator))
    assert retry_reward.status_code == 201
    assert retry_reward.json()["reward_id"] == reward_response.json()["reward_id"]
    changed_reward = await api_client.post(reward_url, json={"total_aceros": 200_000_000},
                                           headers=_auth(creator))
    assert changed_reward.status_code == 409
    denied_retry = await api_client.post(reward_url, json={"total_aceros": 100_000_000},
                                         headers=_auth(reviewer_a))
    assert denied_retry.status_code == 403
    assert reward_response.json()["allocation"]["pools"] == {
        "research_proposer": 1_000_000,
        "final_solution": 10_000_000,
        "participant_contribution_pool": 60_000_000,
        "institutional_validation_pool": 20_000_000,
        "agora_infrastructure": 9_000_000,
    }
    operator_headers = await _login(api_client, f"operator-{unique_name}")
    early_lock = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/lock-reward",
        headers=operator_headers,
    )
    assert early_lock.status_code == 409

    institutions = []
    keys = []
    for label in (f"{unique_name}-a", f"{unique_name}-b"):
        key = SigningKeypair()
        institution, csrf_token = await _register_institution(api_client, label, key)
        institutions.append(institution)
        keys.append(key)
        representative_headers = {"X-CSRF-Token": csrf_token}
        self_verify = await api_client.post(
            f"/v1/research-protocol/institutions/{institution['institution_id']}/verify",
            json={"verification_evidence_hash": hashlib.sha256(label.encode()).hexdigest()},
            headers=representative_headers,
        )
        assert self_verify.status_code == 403
        operator_headers = await _login(api_client, f"operator-{unique_name}")
        verified = await api_client.post(
            f"/v1/research-protocol/institutions/{institution['institution_id']}/verify",
            json={"verification_evidence_hash": hashlib.sha256(label.encode()).hexdigest()},
            headers=operator_headers,
        )
        assert verified.status_code == 200, verified.text

    detail = (await api_client.get(f"/v1/research-protocol/challenges/{mission_id}")).json()
    candidate_detail = detail["candidates"][0]
    review_text = "Independent test review confirms the exact candidate hash and method."
    invalid_payload = {
        "institution_id": institutions[0]["institution_id"],
        "verdict": "APPROVED",
        "methodology_review": review_text,
        "evidence_review": review_text,
        "paper_review": review_text,
        "experiment_review": review_text,
        "conflict_declaration": "No conflict; invalid signature test.",
        "signature": keys[1].sign_b64(b"not-the-bound-candidate-hash"),
    }
    invalid_headers = await _login(api_client, f"institution-{unique_name}-a")
    invalid_review = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reviews",
        json=invalid_payload,
        headers=invalid_headers,
    )
    assert invalid_review.status_code == 403

    accepted_payloads = []
    for index, (institution, key) in enumerate(zip(institutions, keys, strict=True)):
        suffix = "a" if index == 0 else "b"
        payload = {
            "institution_id": institution["institution_id"],
            "verdict": "APPROVED",
            "methodology_review": review_text,
            "evidence_review": review_text,
            "paper_review": review_text,
            "experiment_review": review_text,
            "conflict_declaration": "No conflict; isolated synthetic test institution only.",
        }
        signing_payload = {
            "domain": "agora.institutional.review.v1",
            "candidate_id": candidate["candidate_id"],
            "candidate_content_hash": candidate_detail["content_hash"],
            **payload,
        }
        signed_hash = canonical_json_hash(
            signing_payload, domain="agora.institutional.review.payload.v1"
        )
        headers = await _login(api_client, f"institution-{unique_name}-{suffix}")
        prepared = await api_client.post(
            f"/v1/research-protocol/candidates/{candidate['candidate_id']}/review-signing-payload",
            json=payload,
            headers=headers,
        )
        assert prepared.status_code == 200, prepared.text
        assert prepared.json()["signed_payload_hash"] == signed_hash
        payload["signature"] = key.sign_b64(signed_hash.encode("ascii"))
        accepted_payloads.append(payload)
        blob.unlink()
        missing_review = await api_client.post(
            f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reviews",
            json=payload, headers=headers,
        )
        assert missing_review.status_code == 409
        assert "evidence unavailable" in missing_review.text
        blob.write_bytes(b"original evidence")
        review = await api_client.post(
            f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reviews",
            json=payload,
            headers=headers,
        )
        assert review.status_code == 201, review.text

    duplicate_headers = await _login(api_client, f"institution-{unique_name}-a")
    duplicate_review = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/reviews",
        json=accepted_payloads[0],
        headers=duplicate_headers,
    )
    assert duplicate_review.status_code == 409

    operator_headers = await _login(api_client, f"operator-{unique_name}")
    blob.unlink()
    missing = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/lock-reward",
        headers=operator_headers,
    )
    assert missing.status_code == 409
    assert "evidence unavailable" in missing.text
    blob.write_bytes(b"original evidence")
    locked = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/lock-reward",
        headers=operator_headers,
    )
    assert locked.status_code == 200, locked.text
    assert locked.json()["state"] == "LOCKED"
    locked_detail = (await api_client.get(f"/v1/research-protocol/challenges/{mission_id}")).json()[
        "rewards"
    ][0]
    assert locked_detail["allocation"]["reserved_unallocated"]["institutional_validation_pool"] == 0
    assert len(locked_detail["allocation"]["institutional_validation_pool"]) == 2
    blob.unlink()
    missing = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/publication-package",
        headers=operator_headers,
    )
    assert missing.status_code == 409
    assert "evidence unavailable" in missing.text
    blob.write_bytes(b"original evidence")
    package = await api_client.post(
        f"/v1/research-protocol/candidates/{candidate['candidate_id']}/publication-package",
        headers=operator_headers,
    )
    assert package.status_code == 201, package.text
    assert package.json()["provenance"]["label"] == "Powered by AGORA"
    assert len(package.json()["provenance"]["institutional_reviews"]) == 2

    async with session_factory()() as session:
        transfers_after = (
            await session.execute(select(func.count()).select_from(TokoinLedgerEntry))
        ).scalar_one()
    assert transfers_after == transfers_before
