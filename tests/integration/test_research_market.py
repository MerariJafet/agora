import asyncio

import pytest
from agora_api.db import session_factory
from agora_api.events import Event
from agora_api.models import (
    ResearchCreditReservation,
    ResearchProposal,
    ResearchReleaseEpoch,
)
from sqlalchemy import func, select

from tests.conftest import register_agent

pytestmark = pytest.mark.integration


async def _bootstrap(api_client) -> None:
    response = await api_client.post("/v1/world/magna/bootstrap")
    assert response.status_code == 200, response.text


async def _agent(api_client, keypair, name):
    reg = await register_agent(api_client, keypair, name)
    return reg, {"Authorization": f"Bearer {reg['session_token']}"}


def _proposal(idempotency_key: str, title: str = "Consensus and truth") -> dict:
    return {
        "idempotency_key": idempotency_key,
        "world_id": "research-commons",
        "title": title,
        "beneficial_controller_id": "controller:test:alpha",
        "risk_level": "D1",
        "proposal": {
            "question": "Should AGORA separate audience consensus from scientific truth?",
            "objective": "Produce a reproducible institutional analysis for AGORA governance.",
            "expected_outcome": "A bounded public report with claims, evidence and limitations.",
            "human_value": "Improves safety of autonomous research allocation decisions.",
            "prior_evidence": "Existing AGORA debate and constitution records are public context.",
            "novelty": "Connects social assessment, resource allocation and truth separation.",
            "falsification_condition": "If the argument relies on votes as truth it fails.",
            "method": "Compare constitutional invariants to formal debate and reward semantics.",
            "resources": ["public debate record", "reviewer attention"],
            "risks": "Low risk institutional analysis with no personal data or wet lab work.",
            "rights_status": "Public AGORA-generated context only; no private data required.",
            "closure_criteria": (
                "A reviewed report distinguishes consensus, evidence and settlement."
            ),
            "publication_lane_hint": "OPEN",
        },
    }


def _vector(value: int = 80) -> dict:
    return {
        "idempotency_key": f"assess-{value}",
        "vector": {
            "expected_human_value": value,
            "novelty_and_nonduplication": value,
            "tractability": value,
            "evidence_and_data_availability": value,
            "reproducibility": value,
            "resource_efficiency": value,
            "safety_and_externalities": value,
            "transfer_or_usefulness_potential": value,
        },
        "uncertainty": 10,
    }


async def test_research_proposal_lifecycle_releases_one_test_candidate(
    api_client, keypair, unique_name
):
    await _bootstrap(api_client)
    _, auth = await _agent(api_client, keypair, unique_name)
    created = await api_client.post(
        "/v1/research-market/proposals", json=_proposal("proposal-p1"), headers=auth
    )
    assert created.status_code == 201, created.text
    proposal_id = created.json()["proposal_id"]
    assert created.json()["trust"]["instruction_trust"] == "untrusted_remote"

    submitted = await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/submit-for-eligibility",
        headers=auth,
    )
    assert submitted.status_code == 200, submitted.text

    review = await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/eligibility-reviews",
        json={
            "idempotency_key": "review-p1",
            "decision": "PASS",
            "reason_codes": ["hard_gates_passed"],
        },
        headers=auth,
    )
    assert review.status_code == 201, review.text

    assessment = await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/priority-assessments",
        json=_vector(90),
        headers=auth,
    )
    assert assessment.status_code == 201, assessment.text
    assert assessment.json()["not_truth_score"] is True

    released = await api_client.post(
        "/v1/research-market/epochs/test-run",
        json={"as_of": "2030-01-01T04:01:00Z", "claim_window_seconds": 300},
        headers=auth,
    )
    assert released.status_code == 200, released.text
    body = released.json()
    assert body["outcome"] == "RELEASED"
    assert body["selected_proposal_id"] == proposal_id
    assert body["reservation"]["asset"] == "RESEARCH_CREDITS_TEST"
    assert body["reservation"]["amount_atomic"] == "100000000"
    assert body["real_tokoin_moved"] is False
    assert body["payment_authorized"] is False

    async with session_factory()() as session:
        reservations = (
            await session.execute(select(func.count(ResearchCreditReservation.reservation_id)))
        ).scalar_one()
        epochs = (
            await session.execute(select(func.count(ResearchReleaseEpoch.epoch_id)))
        ).scalar_one()
    assert reservations == 1
    assert epochs == 1


async def test_research_epoch_concurrency_is_idempotent(api_client, keypair, unique_name):
    await _bootstrap(api_client)
    _, auth = await _agent(api_client, keypair, unique_name)
    async with session_factory()() as session:
        reservations_before = (
            await session.execute(select(func.count(ResearchCreditReservation.reservation_id)))
        ).scalar_one()
        events_before = (
            (
                await session.execute(
                    select(Event).where(Event.event_type == "research.candidate.released")
                )
            )
            .scalars()
            .all()
        )
    created = await api_client.post(
        "/v1/research-market/proposals", json=_proposal("p-concurrent"), headers=auth
    )
    proposal_id = created.json()["proposal_id"]
    await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/submit-for-eligibility", headers=auth
    )
    await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/eligibility-reviews",
        json={
            "idempotency_key": "review-concurrent",
            "decision": "PASS",
            "reason_codes": ["hard_gates_passed"],
        },
        headers=auth,
    )
    responses = await asyncio.gather(
        *[
            api_client.post(
                "/v1/research-market/epochs/test-run",
                json={"as_of": "2030-01-01T06:02:00Z", "claim_window_seconds": 300},
                headers=auth,
            )
            for _ in range(10)
        ]
    )
    assert {response.status_code for response in responses} == {200}
    assert {response.json()["outcome"] for response in responses} == {"RELEASED"}
    async with session_factory()() as session:
        reservations = (
            await session.execute(select(func.count(ResearchCreditReservation.reservation_id)))
        ).scalar_one()
        events = (
            (
                await session.execute(
                    select(Event).where(Event.event_type == "research.candidate.released")
                )
            )
            .scalars()
            .all()
        )
    assert reservations - reservations_before == 1
    assert len(events) - len(events_before) == 1


async def test_empty_epoch_and_downtime_do_not_catch_up(api_client, keypair, unique_name):
    await _bootstrap(api_client)
    _, auth = await _agent(api_client, keypair, unique_name)
    empty = await api_client.post(
        "/v1/research-market/epochs/test-run",
        json={"as_of": "2030-01-01T08:01:00Z", "claim_window_seconds": 300},
        headers=auth,
    )
    assert empty.status_code == 200
    assert empty.json()["outcome"] == "NO_ELIGIBLE_CANDIDATE"

    skipped = await api_client.post(
        "/v1/research-market/epochs/test-run",
        json={"as_of": "2030-01-01T10:10:00Z", "claim_window_seconds": 300},
        headers=auth,
    )
    assert skipped.status_code == 200
    assert skipped.json()["outcome"] == "SKIPPED_DOWNTIME"


async def test_research_commitment_pool_and_appeal_are_voluntary(api_client, keypair, unique_name):
    await _bootstrap(api_client)
    _, auth = await _agent(api_client, keypair, unique_name)
    created = await api_client.post(
        "/v1/research-market/proposals", json=_proposal("proposal-p2"), headers=auth
    )
    proposal_id = created.json()["proposal_id"]
    await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/submit-for-eligibility", headers=auth
    )
    await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/eligibility-reviews",
        json={"idempotency_key": "review-p2", "decision": "PASS", "reason_codes": ["ok"]},
        headers=auth,
    )
    commitment = await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/commitments",
        json={
            "idempotency_key": "commit-p2",
            "role": "researcher",
            "beneficial_controller_id": "controller:test:alpha",
            "resource_limits": {"max_hours": 2, "max_compute_label": "local-cpu"},
        },
        headers=auth,
    )
    assert commitment.status_code == 201, commitment.text
    assert commitment.json()["does_not_grant_local_permissions"] is True
    pool = await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/pools",
        json={
            "idempotency_key": "pool-proposal-p2",
            "terms": {
                "summary": "Voluntary collaboration only.",
                "future_split_note": "No settlement occurs in Sprint 2.",
            },
        },
        headers=auth,
    )
    assert pool.status_code == 201, pool.text
    assert pool.json()["terms"]["settlement_executed"] is False
    appeal = await api_client.post(
        f"/v1/research-market/proposals/{proposal_id}/appeals",
        json={
            "idempotency_key": "appeal-p2",
            "target": "selection",
            "reason": "Explain tie break.",
        },
        headers=auth,
    )
    assert appeal.status_code == 201


async def test_duplicate_links_and_lifecycle_actions_are_auditable(
    api_client, keypair, unique_name
):
    await _bootstrap(api_client)
    _, auth = await _agent(api_client, keypair, unique_name)
    first = await api_client.post(
        "/v1/research-market/proposals",
            json=_proposal("duplicate-a", title="Consensus and truth A"),
        headers=auth,
    )
    second = await api_client.post(
        "/v1/research-market/proposals",
            json=_proposal("duplicate-b", title="Consensus and truth B"),
        headers=auth,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    source_id = first.json()["proposal_id"]
    target_id = second.json()["proposal_id"]

    linked = await api_client.post(
        f"/v1/research-market/proposals/{source_id}/duplicate-links",
        json={"target_proposal_id": target_id, "link_type": "semantic", "confidence": 82},
        headers=auth,
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["semantic_result_not_auto_rejection"] is True

    dormant = await api_client.post(
        f"/v1/research-market/proposals/{source_id}/actions",
        json={"action": "signal_dormant", "reason": "No current reviewer capacity."},
        headers=auth,
    )
    assert dormant.status_code == 200, dormant.text
    assert dormant.json()["state"] == "DORMANT"
    assert "reopen" in dormant.json()["next_allowed_actions"]


async def test_research_market_summary_is_read_only_and_honest(api_client):
    async with session_factory()() as session:
        before = (
            await session.execute(select(func.count(ResearchProposal.proposal_id)))
        ).scalar_one()
    summary = await api_client.get("/v1/research-market")
    assert summary.status_code == 200
    body = summary.json()
    assert body["scheduler_enabled"] is True
    assert body["asset"]["real_tokoin"] is False
    assert body["asset"]["wallets_created"] is False
    async with session_factory()() as session:
        after = (
            await session.execute(select(func.count(ResearchProposal.proposal_id)))
        ).scalar_one()
    assert after == before


async def test_thirty_day_simulation_is_read_only(api_client, keypair, unique_name):
    await _bootstrap(api_client)
    _, auth = await _agent(api_client, keypair, unique_name)
    async with session_factory()() as session:
        before = (
            await session.execute(select(func.count(ResearchReleaseEpoch.epoch_id)))
        ).scalar_one()
    simulated = await api_client.post(
        "/v1/research-market/epochs/simulate-30-days",
        json={"start_at": "2030-01-01T00:00:00Z", "days": 30},
        headers=auth,
    )
    assert simulated.status_code == 200, simulated.text
    body = simulated.json()
    assert body["epochs"] == 360
    assert body["max_possible_releases"] == 360
    assert body["mutates_database"] is False
    async with session_factory()() as session:
        after = (
            await session.execute(select(func.count(ResearchReleaseEpoch.epoch_id)))
        ).scalar_one()
    assert after == before
