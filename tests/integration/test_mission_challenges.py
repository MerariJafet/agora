from datetime import timedelta

import pytest
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.ids import new_mission_id, new_space_id
from agora_api.mission_challenges_service import COLLATZ_MISSION_ID
from agora_api.models import Mission, Space, TokoinLedgerEntry
from agora_api.provenance import add_provenance
from agora_api.tokoins_service import ACEROS_PER_TOKOIN
from sqlalchemy import select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _seed_challenge(api_client, unique_name: str) -> tuple[dict, dict]:
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-creator")
    mission_id = new_mission_id()
    space_id = new_space_id()
    async with session_factory()() as session:
        session.add(
            Space(
                space_id=space_id,
                slug=f"challenge-{unique_name.lower()}",
                name=f"Challenge {unique_name}",
                kind="mission_challenge",
                description="Ephemeral test challenge space.",
                evidence_policy="optional",
                created_at=now_utc(),
            )
        )
        await add_provenance(
            session,
            record_table="spaces",
            record_id=space_id,
            created_by="test.seed_challenge",
            source_reference=unique_name,
        )
        session.add(
            Mission(
                mission_id=mission_id,
                title=f"Challenge {unique_name}",
                objective="Solve a bounded deterministic research challenge.",
                description="Participants must submit argument plus experiments.",
                state="active",
                visibility="public",
                hosting_space_id=space_id,
                related_claim_ids=[],
                deadline_at=now_utc() + timedelta(hours=24),
                reward_aceros=ACEROS_PER_TOKOIN,
                challenge_kind="math_unsolved",
                challenge_problem={"name": "Test Collatz-style problem", "status": "unsolved"},
                challenge_space_color="#35d0ff",
                resolution_policy="unanimous_participant_review_except_submitter",
                max_participants=8,
                completion_policy={
                    "challenge_deadline_hours": 24,
                    "reward_aceros": ACEROS_PER_TOKOIN,
                },
                created_by_agent_id=creator["agent_id"],
                created_by_agent_version_id=creator["agent_version_id"],
                created_at=now_utc(),
                activated_at=now_utc(),
            )
        )
        await add_provenance(
            session,
            record_table="missions",
            record_id=mission_id,
            created_by="test.seed_challenge",
            source_reference=unique_name,
        )
        await session.commit()
    return creator, {"mission_id": mission_id, "space_id": space_id}


async def _join(api_client, mission_id: str, reg: dict) -> None:
    response = await api_client.post(
        f"/v1/mission-challenges/{mission_id}/join", headers=_auth(reg)
    )
    assert response.status_code == 201, response.text


async def _cancel_test_challenge(mission_id: str) -> None:
    async with session_factory()() as session:
        mission = await session.get(Mission, mission_id)
        if mission is not None and mission.title.startswith("Challenge TestAgent-"):
            mission.state = "cancelled"
            await session.commit()


async def _submit(api_client, mission_id: str, reg: dict) -> dict:
    response = await api_client.post(
        f"/v1/mission-challenges/{mission_id}/submissions",
        json={
            "idempotency_key": f"submit-{reg['agent_id']}",
            "solution_summary": "This is a deliberate proposed resolution with enough detail.",
            "claim_ids": [],
            "artifact_version_ids": [],
            "evidence_ids": [],
            "limitations": "This bounded test result is not a general mathematical proof.",
            "public_rationale": (
                "The Agent presents a public argument, explicit limitations and no private "
                "chain-of-thought. This is enough structured material for peer review."
            ),
            "reasoning_outline": (
                "The Agent presents a public argument, explicit limitations and no private "
                "chain-of-thought. This is enough structured material for peer review."
            ),
            "experiments": {"checked_range": "1..1000000", "counterexample": None},
        },
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_collatz_challenge_seeded_and_visible_in_world(api_client):
    active = (await api_client.get("/v1/mission-challenges/active")).json()
    seeded = [
        item for item in active["mission_challenges"]
        if item["mission_id"] == COLLATZ_MISSION_ID
    ]
    assert seeded, active
    challenge = seeded[0]
    assert challenge["challenge_problem"]["name"] == "Collatz conjecture"
    assert challenge["reward_aceros"] == ACEROS_PER_TOKOIN
    assert challenge["deadline_at"]

    manifest = (await api_client.get("/v1/world/manifest")).json()
    landmarks = [
        item for item in manifest["landmarks"]
        if item.get("mission_id") == COLLATZ_MISSION_ID
    ]
    assert landmarks
    assert landmarks[0]["color"] == "#35d0ff"
    assert landmarks[0]["shape"] == "challenge"


async def test_public_space_listing_hides_inactive_synthetic_challenge_spaces(
    api_client, unique_name
):
    _, challenge = await _seed_challenge(api_client, unique_name)
    try:
        active_spaces = (await api_client.get("/v1/spaces")).json()["spaces"]
        active_slugs = {space["slug"] for space in active_spaces}
        assert f"challenge-{unique_name.lower()}" in active_slugs

        await _cancel_test_challenge(challenge["mission_id"])

        filtered_spaces = (await api_client.get("/v1/spaces")).json()["spaces"]
        filtered_slugs = {space["slug"] for space in filtered_spaces}
        assert "collatz-challenge-24h" in filtered_slugs
        assert f"challenge-{unique_name.lower()}" not in filtered_slugs
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_unanimous_votes_award_one_tokoin(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter_a = await register_agent(api_client, SigningKeypair(), f"{unique_name}-voter-a")
    voter_b = await register_agent(api_client, SigningKeypair(), f"{unique_name}-voter-b")
    for reg in (submitter, voter_a, voter_b):
        await _join(api_client, challenge["mission_id"], reg)

    before = (
        await api_client.get(f"/v1/agents/{submitter['agent_id']}/wallet")
    ).json()["balance_aceros"]
    submission = await _submit(api_client, challenge["mission_id"], submitter)
    first_vote = await api_client.post(
        f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
        json={
            "idempotency_key": f"vote-{voter_a['agent_id']}",
            "verdict": "resolved",
            "review_evidence_ids": [],
            "public_rationale": "The argument appears complete enough to accept.",
            "conflict_of_interest_declaration": "none",
        },
        headers=_auth(voter_a),
    )
    assert first_vote.status_code == 200, first_vote.text
    assert first_vote.json()["resolved"] is False

    second_vote = await api_client.post(
        f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
        json={
            "idempotency_key": f"vote-{voter_b['agent_id']}",
            "verdict": "resolved",
            "review_evidence_ids": [],
            "public_rationale": "I independently accept the proposed resolution.",
            "conflict_of_interest_declaration": "none",
        },
        headers=_auth(voter_b),
    )
    assert second_vote.status_code == 200, second_vote.text
    body = second_vote.json()
    assert body["resolved"] is True
    assert body["mission"]["state"] == "completed"

    after = (
        await api_client.get(f"/v1/agents/{submitter['agent_id']}/wallet")
    ).json()["balance_aceros"]
    assert after - before == ACEROS_PER_TOKOIN


async def test_submitter_cannot_vote_for_own_solution(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    try:
        await _join(api_client, challenge["mission_id"], submitter)
        submission = await _submit(api_client, challenge["mission_id"], submitter)

        response = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
            json={
                "idempotency_key": f"vote-{submitter['agent_id']}",
                "verdict": "resolved",
                "review_evidence_ids": [],
                "public_rationale": "Self-review should not count.",
                "conflict_of_interest_declaration": "self",
            },
            headers=_auth(submitter),
        )
        assert response.status_code == 403
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_negative_vote_keeps_challenge_open(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-voter")
    try:
        for reg in (submitter, voter):
            await _join(api_client, challenge["mission_id"], reg)
        submission = await _submit(api_client, challenge["mission_id"], submitter)

        response = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
            json={
                "idempotency_key": f"vote-{voter['agent_id']}",
                "verdict": "not_resolved",
                "review_evidence_ids": [],
                "public_rationale": "The reasoning does not close all cases.",
                "conflict_of_interest_declaration": "none",
            },
            headers=_auth(voter),
        )
        assert response.status_code == 200, response.text
        assert response.json()["resolved"] is False
        challenge_state = (
            await api_client.get(f"/v1/mission-challenges/{challenge['mission_id']}")
        ).json()
        assert challenge_state["state"] == "active"
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_duplicate_submit_retry_returns_same_submission(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    try:
        await _join(api_client, challenge["mission_id"], submitter)
        first = await _submit(api_client, challenge["mission_id"], submitter)
        second = await _submit(api_client, challenge["mission_id"], submitter)
        assert second["submission_id"] == first["submission_id"]
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_abstention_does_not_deadlock_unanimous_resolution(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-voter")
    abstainer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-abstainer")
    try:
        for reg in (submitter, voter, abstainer):
            await _join(api_client, challenge["mission_id"], reg)
        before = (
            await api_client.get(f"/v1/agents/{submitter['agent_id']}/wallet")
        ).json()["balance_aceros"]
        submission = await _submit(api_client, challenge["mission_id"], submitter)
        abstained = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/abstentions",
            json={
                "idempotency_key": f"abstain-{abstainer['agent_id']}",
                "reason": "I lack enough independent evidence and abstain without blocking.",
            },
            headers=_auth(abstainer),
        )
        assert abstained.status_code == 200, abstained.text
        assert abstained.json()["resolved"] is False

        accepted = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
            json={
                "idempotency_key": f"vote-{voter['agent_id']}",
                "verdict": "resolved",
                "review_evidence_ids": [],
                "public_rationale": "The only non-abstaining reviewer accepts this result.",
                "conflict_of_interest_declaration": "none",
            },
            headers=_auth(voter),
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["resolved"] is True
        replay = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
            json={
                "idempotency_key": f"vote-{voter['agent_id']}",
                "verdict": "resolved",
                "review_evidence_ids": [],
                "public_rationale": "The only non-abstaining reviewer accepts this result.",
                "conflict_of_interest_declaration": "none",
            },
            headers=_auth(voter),
        )
        assert replay.status_code == 409
        after = (
            await api_client.get(f"/v1/agents/{submitter['agent_id']}/wallet")
        ).json()["balance_aceros"]
        assert after - before == ACEROS_PER_TOKOIN
        async with session_factory()() as session:
            reward_entries = (
                await session.execute(
                    select(TokoinLedgerEntry).where(
                        TokoinLedgerEntry.mission_id == challenge["mission_id"],
                        TokoinLedgerEntry.entry_type == "mission_reward",
                    )
                )
            ).scalars().all()
            assert len(reward_entries) == 1
    finally:
        await _cancel_test_challenge(challenge["mission_id"])
