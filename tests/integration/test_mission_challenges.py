from datetime import timedelta

import pytest
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.ids import new_evidence_id, new_mission_id, new_space_id
from agora_api.mission_challenges_service import COLLATZ_MISSION_ID, expire_due_challenges
from agora_api.models import (
    Event,
    Evidence,
    ForumPost,
    Mission,
    MissionChallengeSubmission,
    RecordProvenance,
    Space,
    TokoinLedgerEntry,
)
from agora_api.provenance import add_provenance
from agora_api.tokoins_service import ACEROS_PER_TOKOIN
from sqlalchemy import select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


def _methodology() -> dict:
    return {
        "hypothesis": "A bounded public claim can be checked by independent reviewers.",
        "novelty_check": "The test harness treats this as an unresolved local challenge case.",
        "method_type": "computational_experiment",
        "verification_plan": (
            "Review public rationale, artifacts and deterministic evidence metadata."
        ),
        "falsifiability": (
            "A missing argument, counterexample or unreproducible run refutes acceptance."
        ),
        "reproducibility": (
            "Another agent can inspect the same public fields and rerun the test path."
        ),
        "evidence_standard": "replicable_computation",
        "limitations": "This validates AGORA challenge mechanics rather than solving real science.",
    }


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
                challenge_problem={"name": "Test bounded problem", "status": "unsolved"},
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


async def _submit(
    api_client, mission_id: str, reg: dict, *, team_agent_ids: list[str] | None = None
) -> dict:
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
            "methodology": _methodology(),
            **({"team_agent_ids": team_agent_ids} if team_agent_ids else {}),
        },
        headers=_auth(reg),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _seed_evidence(unique_name: str, reg: dict) -> str:
    evidence_id = new_evidence_id()
    async with session_factory()() as session:
        session.add(
            Evidence(
                evidence_id=evidence_id,
                source_type="other",
                locator=f"local-test://{unique_name}/experiment-log",
                provenance_level="client_hashed_snapshot",
                title=f"{unique_name} bounded experiment log",
                excerpt="Bounded deterministic experiment metadata for challenge review.",
                publisher="AGORA test harness",
                content_hash="0" * 64,
                observed_at=now_utc(),
                published_at=None,
                created_by_agent_id=reg["agent_id"],
                created_at=now_utc(),
            )
        )
        await add_provenance(
            session,
            record_table="evidence",
            record_id=evidence_id,
            created_by="test.seed_evidence",
            source_reference=unique_name,
            created_by_actor_id=reg["agent_id"],
            created_by_actor_provenance="test",
        )
        await session.commit()
    return evidence_id


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


async def test_formal_action_plane_capabilities_are_discoverable(api_client, unique_name):
    _, challenge = await _seed_challenge(api_client, unique_name)
    try:
        response = await api_client.get(
            f"/v1/mission-challenges/{challenge['mission_id']}/capabilities"
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["capabilities"]["capability_manifest_version"] == "formal-action-plane.v1"
        assert body["capabilities"]["research_challenge_rules"]["preferred_solution_flow"] == [
            "publish_artifact_version",
            "submit_challenge_solution",
        ]
        assert "review_vote_guidance" in body["capabilities"]["research_challenge_rules"]
        action_names = {action["name"] for action in body["capabilities"]["actions"]}
        assert {
            "join_challenge",
            "create_submission_draft",
            "attach_submission_evidence",
            "finalize_submission",
            "vote_challenge_solution",
        }.issubset(action_names)
        assert body["generic_next_allowed_actions"][0]["name"] == "join_challenge"
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_collatz_challenge_requires_primary_evidence_fields(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-evidence-voter")
    async with session_factory()() as session:
        mission = await session.get(Mission, challenge["mission_id"])
        assert mission is not None
        mission.title = f"Challenge {unique_name} Collatz"
        mission.challenge_problem = {"name": "Collatz conjecture", "status": "unsolved"}
        await session.commit()
    await _join(api_client, challenge["mission_id"], submitter)
    await _join(api_client, challenge["mission_id"], voter)
    try:
        rejected = await api_client.post(
            f"/v1/mission-challenges/{challenge['mission_id']}/submissions",
            json={
                "idempotency_key": f"bad-collatz-{submitter['agent_id']}",
                "solution_summary": "This Collatz submission lacks primary computable evidence.",
                "claim_ids": [],
                "artifact_version_ids": [],
                "evidence_ids": [],
                "limitations": "The payload intentionally omits required evidence fields.",
                "public_rationale": (
                    "A public rationale exists, but it does not include machine-readable "
                    "range, rule, extreme case, trace or checksum."
                ),
                "experiments": {"checked_range": "1..1000"},
                "methodology": _methodology(),
            },
            headers=_auth(submitter),
        )
        assert rejected.status_code == 422, rejected.text
        assert "range, rule, extreme_case" in rejected.text

        accepted = await api_client.post(
            f"/v1/mission-challenges/{challenge['mission_id']}/submissions",
            json={
                "idempotency_key": f"good-collatz-{submitter['agent_id']}",
                "solution_summary": "Bounded Collatz trace validates every n in range 1..1000.",
                "claim_ids": [],
                "artifact_version_ids": [],
                "evidence_ids": [],
                "limitations": "This is bounded computation, not a proof of the conjecture.",
                "public_rationale": (
                    "The proposal exposes the checked range, transition rule, extreme case "
                    "and checksum so reviewers can reproduce the bounded computation."
                ),
                "experiments": {
                    "range": "1..1000",
                    "rule": "n/2 if even else 3n+1 until 1",
                    "extreme_case": {"n": 871, "steps": 178},
                    "checksum": "sha256:bounded-collatz-test-checksum",
                },
                "methodology": _methodology(),
            },
            headers=_auth(submitter),
        )
        assert accepted.status_code == 201, accepted.text
        detail = (
            await api_client.get(f"/v1/mission-challenges/{challenge['mission_id']}")
        ).json()
        assert detail["primary_evidence_requirements"]["problem_family"] == "collatz"
        assert detail["agent_entry_instruction"]["challenge_loop"] == [
            "join",
            "inspect_submissions",
            "publish_artifact_version_when_possible",
            "submit_with_methodology_and_primary_evidence",
            "vote_or_abstain_with_reason",
            "reframe_after_feedback_when_allowed",
        ]
        assert detail["recommended_solution_flow"][:2] == [
            "publish_artifact_version",
            "submit_challenge_solution",
        ]
        voter_caps = (
            await api_client.get(
                f"/v1/mission-challenges/{challenge['mission_id']}/capabilities/me",
                headers=_auth(voter),
            )
        ).json()
        vote_action = next(
            action for action in voter_caps["agent_next_allowed_actions"]
            if action["name"] == "vote_challenge_solution"
            and action.get("submission_id") == accepted.json()["submission_id"]
        )
        assert vote_action["evidence_assessment"]["status"] == "primary_evidence_missing"
        assert "missing_primary_reference_ids" in vote_action["evidence_assessment"]["blockers"]
        assert vote_action["recommended_verdict_when_blocked"] == "abstain"
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_global_formal_action_plane_capabilities_are_discoverable(api_client):
    response = await api_client.get("/v1/mission-challenges/capabilities")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capabilities"]["capability_manifest_version"] == "formal-action-plane.v1"
    action_names = {action["name"] for action in body["capabilities"]["actions"]}
    assert "join_challenge" in action_names
    assert body["generic_next_allowed_actions"][0]["name"] == "inspect_capabilities"


async def test_agent_specific_challenge_capabilities_enable_submit_vote_and_abstain(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-capability-voter")
    try:
        unauthenticated = await api_client.get(
            f"/v1/mission-challenges/{challenge['mission_id']}/capabilities/me"
        )
        assert unauthenticated.status_code == 401

        await _join(api_client, challenge["mission_id"], submitter)
        submitter_caps = (
            await api_client.get(
                f"/v1/mission-challenges/{challenge['mission_id']}/capabilities/me",
                headers=_auth(submitter),
            )
        ).json()
        submitter_actions = {
            action["name"]: action
            for action in submitter_caps["agent_next_allowed_actions"]
        }
        assert submitter_caps["agent_id"] == submitter["agent_id"]
        assert submitter_actions["submit_challenge_solution"]["allowed"] is True

        submission = await _submit(api_client, challenge["mission_id"], submitter)
        await _join(api_client, challenge["mission_id"], voter)
        voter_caps = (
            await api_client.get(
                f"/v1/mission-challenges/{challenge['mission_id']}/capabilities/me",
                headers=_auth(voter),
            )
        ).json()
        vote_actions = [
            action for action in voter_caps["agent_next_allowed_actions"]
            if action["name"] == "vote_challenge_solution"
        ]
        abstain_actions = [
            action for action in voter_caps["agent_next_allowed_actions"]
            if action["name"] == "abstain_challenge_vote"
        ]
        assert {
            action["submission_id"] for action in vote_actions if action["allowed"]
        } == {submission["submission_id"]}
        assert {
            action["submission_id"] for action in abstain_actions if action["allowed"]
        } == {submission["submission_id"]}
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


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


async def test_due_challenge_records_deadline_without_winner_submission_or_reward(
    api_client, unique_name
):
    _, challenge = await _seed_challenge(api_client, unique_name)
    async with session_factory()() as session:
        mission = await session.get(Mission, challenge["mission_id"])
        assert mission is not None
        mission.deadline_at = now_utc() - timedelta(minutes=1)
        await session.commit()

        elapsed = await expire_due_challenges(session, trace_id="a" * 32)
        await session.commit()

        assert elapsed >= 1
        await session.refresh(mission)
        assert mission.state == "active"
        assert mission.winning_submission_id is None
        assert mission.resolved_by_agent_id is None
        assert mission.resolved_at is None

        submissions = (
            await session.execute(
                select(MissionChallengeSubmission).where(
                    MissionChallengeSubmission.mission_id == challenge["mission_id"]
                )
            )
        ).scalars().all()
        rewards = (
            await session.execute(
                select(TokoinLedgerEntry).where(
                    TokoinLedgerEntry.mission_id == challenge["mission_id"]
                )
            )
        ).scalars().all()
        events = (
            await session.execute(
                select(Event).where(
                    Event.event_type == "mission.challenge_deadline_elapsed",
                    Event.payload["mission_id"].as_string() == challenge["mission_id"],
                )
            )
        ).scalars().all()
        assert submissions == []
        assert rewards == []
        assert len(events) == 1
        assert events[0].payload["outcome"] == "UNRESOLVED_CONTINUES"
        assert events[0].payload["closes_challenge"] is False
        assert events[0].payload["event_class"] == "lifecycle_system"
    await _cancel_test_challenge(challenge["mission_id"])


async def test_challenge_deadline_elapsed_is_idempotent_across_scheduler_restarts(
    api_client, unique_name
):
    _, challenge = await _seed_challenge(api_client, unique_name)
    async with session_factory()() as session:
        mission = await session.get(Mission, challenge["mission_id"])
        assert mission is not None
        mission.deadline_at = now_utc() - timedelta(minutes=1)
        await session.commit()

    async with session_factory()() as first_session:
        first = await expire_due_challenges(first_session, trace_id="b" * 32)
        await first_session.commit()
    async with session_factory()() as second_session:
        second = await expire_due_challenges(second_session, trace_id="c" * 32)
        await second_session.commit()
        events = (
            await second_session.execute(
                select(Event).where(
                    Event.event_type == "mission.challenge_deadline_elapsed",
                    Event.payload["mission_id"].as_string() == challenge["mission_id"],
                )
            )
        ).scalars().all()

    assert first == 1
    assert second == 0
    assert len(events) == 1
    await _cancel_test_challenge(challenge["mission_id"])


async def test_deadline_elapsed_does_not_block_late_resolution(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-late-voter")
    for reg in (submitter, voter):
        await _join(api_client, challenge["mission_id"], reg)
    async with session_factory()() as session:
        mission = await session.get(Mission, challenge["mission_id"])
        assert mission is not None
        mission.deadline_at = now_utc() - timedelta(minutes=5)
        await session.commit()
        elapsed = await expire_due_challenges(session, trace_id="d" * 32)
        await session.commit()
        assert elapsed >= 1

    deadline_view = (
        await api_client.get(f"/v1/mission-challenges/{challenge['mission_id']}")
    ).json()
    assert deadline_view["state"] == "active"
    assert deadline_view["deadline_elapsed"] is True
    assert deadline_view["deadline_status"] == "elapsed_unresolved"
    assert deadline_view["deadline_closes_challenge"] is False

    submission = await _submit(api_client, challenge["mission_id"], submitter)
    vote = await api_client.post(
        f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
        json={
            "idempotency_key": f"vote-{voter['agent_id']}",
            "verdict": "resolved",
            "review_evidence_ids": [],
            "public_rationale": "The late public solution remains reviewable after deadline.",
            "conflict_of_interest_declaration": "none",
        },
        headers=_auth(voter),
    )
    assert vote.status_code == 200, vote.text
    assert vote.json()["resolved"] is True
    assert vote.json()["mission"]["state"] == "completed"


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


async def test_resolved_challenge_splits_one_percent_to_proposer_and_team_winner_pool(
    api_client, unique_name
):
    proposer, challenge = await _seed_challenge(api_client, unique_name)
    worker = await register_agent(api_client, SigningKeypair(), f"{unique_name}-worker")
    teammate = await register_agent(api_client, SigningKeypair(), f"{unique_name}-teammate")
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-team-voter")
    for reg in (worker, teammate, voter):
        await _join(api_client, challenge["mission_id"], reg)

    before_proposer = (
        await api_client.get(f"/v1/agents/{proposer['agent_id']}/wallet")
    ).json()["balance_aceros"]
    before_worker = (
        await api_client.get(f"/v1/agents/{worker['agent_id']}/wallet")
    ).json()["balance_aceros"]
    before_teammate = (
        await api_client.get(f"/v1/agents/{teammate['agent_id']}/wallet")
    ).json()["balance_aceros"]
    submission = await _submit(
        api_client,
        challenge["mission_id"],
        worker,
        team_agent_ids=[worker["agent_id"], teammate["agent_id"]],
    )
    vote = await api_client.post(
        f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
        json={
            "idempotency_key": f"vote-{voter['agent_id']}",
            "verdict": "resolved",
            "review_evidence_ids": [],
            "public_rationale": "The declared team result is accepted for the split test.",
            "conflict_of_interest_declaration": "none",
        },
        headers=_auth(voter),
    )
    assert vote.status_code == 200, vote.text
    assert vote.json()["resolved"] is True
    assert vote.json()["submission"]["team_agent_ids"] == [worker["agent_id"], teammate["agent_id"]]

    after_proposer = (
        await api_client.get(f"/v1/agents/{proposer['agent_id']}/wallet")
    ).json()["balance_aceros"]
    after_worker = (
        await api_client.get(f"/v1/agents/{worker['agent_id']}/wallet")
    ).json()["balance_aceros"]
    after_teammate = (
        await api_client.get(f"/v1/agents/{teammate['agent_id']}/wallet")
    ).json()["balance_aceros"]
    assert after_proposer - before_proposer == 1_000_000
    assert after_worker - before_worker == 49_500_000
    assert after_teammate - before_teammate == 49_500_000
    async with session_factory()() as session:
        reward_entries = (
            await session.execute(
                select(TokoinLedgerEntry).where(
                    TokoinLedgerEntry.mission_id == challenge["mission_id"],
                    TokoinLedgerEntry.entry_type == "mission_reward",
                )
            )
        ).scalars().all()
    assert len(reward_entries) == 3
    assert sum(entry.amount for entry in reward_entries) == ACEROS_PER_TOKOIN


async def test_zero_reward_challenge_resolution_does_not_default_to_tokoin(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-zero-voter")
    async with session_factory()() as session:
        mission = await session.get(Mission, challenge["mission_id"])
        assert mission is not None
        mission.reward_aceros = 0
        mission.completion_policy = {"reward_aceros": 0}
        await session.commit()
    for reg in (submitter, voter):
        await _join(api_client, challenge["mission_id"], reg)

    before = (
        await api_client.get(f"/v1/agents/{submitter['agent_id']}/wallet")
    ).json()["balance_aceros"]
    submission = await _submit(api_client, challenge["mission_id"], submitter)
    vote = await api_client.post(
        f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
        json={
            "idempotency_key": f"vote-{voter['agent_id']}",
            "verdict": "resolved",
            "review_evidence_ids": [],
            "public_rationale": "I independently accept the proposed resolution.",
            "conflict_of_interest_declaration": "none",
        },
        headers=_auth(voter),
    )
    assert vote.status_code == 200, vote.text
    assert vote.json()["resolved"] is True

    after = (
        await api_client.get(f"/v1/agents/{submitter['agent_id']}/wallet")
    ).json()["balance_aceros"]
    async with session_factory()() as session:
        reward_entries = (
            await session.execute(
                select(TokoinLedgerEntry).where(
                    TokoinLedgerEntry.mission_id == challenge["mission_id"],
                    TokoinLedgerEntry.entry_type == "mission_reward",
                )
            )
        ).scalars().all()
    assert after == before
    assert reward_entries == []


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


async def test_challenge_views_report_real_submission_and_vote_counts(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-count-voter")
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
                "public_rationale": "The proposed resolution remains incomplete.",
                "conflict_of_interest_declaration": "none",
            },
            headers=_auth(voter),
        )
        assert response.status_code == 200, response.text

        active = (await api_client.get("/v1/mission-challenges/active")).json()
        visible = [
            item
            for item in active["mission_challenges"]
            if item["mission_id"] == challenge["mission_id"]
        ]
        assert visible
        assert visible[0]["submissions_count"] == 1
        assert visible[0]["votes_count"] == 1
        assert visible[0]["resolved_votes"] == 0
        assert visible[0]["submissions"][0]["submission_id"] == submission["submission_id"]
        assert visible[0]["submissions"][0]["votes_count"] == 1

        detail = (
            await api_client.get(f"/v1/mission-challenges/{challenge['mission_id']}")
        ).json()
        assert detail["submissions_count"] == 1
        assert detail["votes_count"] == 1
        assert detail["submissions"][0]["votes_count"] == 1
        assert detail["submissions"][0]["resolved_votes"] == 0
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


async def test_formal_draft_evidence_finalize_and_test_reward_provenance(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-formal-voter")
    try:
        for reg in (submitter, voter):
            await _join(api_client, challenge["mission_id"], reg)
        evidence_id = await _seed_evidence(unique_name, submitter)

        draft = await api_client.post(
            f"/v1/mission-challenges/{challenge['mission_id']}/submission-drafts",
            json={
                "idempotency_key": f"draft-{submitter['agent_id']}",
                "solution_summary": "Draft: candidate result under construction.",
                "public_rationale": "I am preparing a bounded public argument.",
            },
            headers=_auth(submitter),
        )
        assert draft.status_code == 201, draft.text
        draft_body = draft.json()
        submission_id = draft_body["submission"]["submission_id"]
        assert draft_body["submission"]["state"] == "draft"
        assert draft_body["receipt"]["action"] == "create_submission_draft"
        assert any(
            action["name"] == "finalize_submission"
            and action["submission_id"] == submission_id
            for action in draft_body["next_allowed_actions"]
        )

        attached = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/evidence",
            json={
                "idempotency_key": f"evidence-{submitter['agent_id']}",
                "evidence_ids": [evidence_id],
            },
            headers=_auth(submitter),
        )
        assert attached.status_code == 200, attached.text
        assert attached.json()["submission"]["evidence_ids"] == [evidence_id]
        assert attached.json()["receipt"]["action"] == "attach_submission_evidence"

        finalized = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/finalize",
            json={
                "idempotency_key": f"finalize-{submitter['agent_id']}",
                "solution_summary": "A formal public challenge solution is ready for review.",
                "claim_ids": [],
                "artifact_version_ids": [],
                "evidence_ids": [evidence_id],
                "limitations": "This test proves the institutional flow, not Collatz itself.",
                "public_rationale": (
                    "The submission contains a public summary, explicit limitations and "
                    "attached evidence metadata; no private reasoning is required."
                ),
                "reasoning_outline": "Bounded public outline only.",
                "experiments": {"checked_range": "deterministic-test"},
                "methodology": _methodology(),
            },
            headers=_auth(submitter),
        )
        assert finalized.status_code == 200, finalized.text
        assert finalized.json()["submission"]["state"] == "submitted"
        assert finalized.json()["receipt"]["action"] == "finalize_submission"

        vote = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/votes",
            json={
                "idempotency_key": f"vote-{voter['agent_id']}",
                "verdict": "resolved",
                "review_evidence_ids": [evidence_id],
                "public_rationale": "The formal evidence trail is sufficient for this test.",
                "conflict_of_interest_declaration": "none",
            },
            headers=_auth(voter),
        )
        assert vote.status_code == 200, vote.text
        assert vote.json()["resolved"] is True

        async with session_factory()() as session:
            reward_entries = (
                await session.execute(
                    select(TokoinLedgerEntry).where(
                        TokoinLedgerEntry.mission_id == challenge["mission_id"],
                        TokoinLedgerEntry.entry_type == "mission_reward",
                    )
                )
            ).scalars().all()
            assert len(reward_entries) == 2
            assert sum(entry.amount for entry in reward_entries) == ACEROS_PER_TOKOIN
            provenance = await session.get(
                RecordProvenance,
                ("tokoin_ledger_entries", reward_entries[0].entry_id),
            )
            assert provenance is not None
            assert provenance.provenance_class == "test"
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_draft_submission_cannot_be_reviewed(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-draft-voter")
    try:
        for reg in (submitter, voter):
            await _join(api_client, challenge["mission_id"], reg)
        draft = await api_client.post(
            f"/v1/mission-challenges/{challenge['mission_id']}/submission-drafts",
            json={"idempotency_key": f"draft-{submitter['agent_id']}"},
            headers=_auth(submitter),
        )
        assert draft.status_code == 201, draft.text
        submission_id = draft.json()["submission"]["submission_id"]
        vote = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/votes",
            json={
                "idempotency_key": f"vote-{voter['agent_id']}",
                "verdict": "resolved",
                "review_evidence_ids": [],
                "public_rationale": "A draft must not be reviewable.",
                "conflict_of_interest_declaration": "none",
            },
            headers=_auth(voter),
        )
        assert vote.status_code == 409
        assert vote.json()["error"]["code"] == "conflict"
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
        rationales = abstained.json()["submission"]["review_rationales"]
        assert rationales == [
            {
                "voter_agent_id": abstainer["agent_id"],
                "verdict": "abstain",
                "resolved": False,
                "abstained": True,
                "public_rationale": (
                    "I lack enough independent evidence and abstain without blocking."
                ),
                "review_evidence_ids": [],
                "created_at": rationales[0]["created_at"],
            }
        ]

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
        final_artifact_ids = accepted.json()["mission"]["final_artifact_version_ids"]
        assert len(final_artifact_ids) == 1
        paper_version_id = final_artifact_ids[0]
        paper = (await api_client.get(f"/v1/artifact-versions/{paper_version_id}")).json()
        assert paper["state"] == "published"
        assert paper["media_type"] == "text/markdown"
        assert paper["provenance_manifest"]["mission_id"] == challenge["mission_id"]
        assert paper["provenance_manifest"]["source_evidence_ids"] == []
        download = await api_client.get(f"/v1/artifact-versions/{paper_version_id}/download")
        assert download.status_code == 200
        assert download.headers["x-content-type-options"] == "nosniff"
        paper_text = download.text
        assert "challenge_resolution_paper" in paper_text
        assert '"status": "RESOLVED_VERIFIED"' in paper_text
        assert '"tokoin"' in paper_text
        assert '"review"' in paper_text
        assert '"methodology"' in paper_text
        assert "does not equate consensus with truth" in paper_text
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
            assert len(reward_entries) == 2
            assert sum(entry.amount for entry in reward_entries) == ACEROS_PER_TOKOIN
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_abstention_requires_public_evaluation_argument(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    abstainer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-abstainer")
    try:
        for reg in (submitter, abstainer):
            await _join(api_client, challenge["mission_id"], reg)
        submission = await _submit(api_client, challenge["mission_id"], submitter)
        rejected = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/abstentions",
            json={
                "idempotency_key": f"abstain-{abstainer['agent_id']}",
                "reason": "          ",
            },
            headers=_auth(abstainer),
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "validation_failed"
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_submitter_can_reframe_argument_after_abstention_feedback(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    abstainer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-abstainer")
    try:
        for reg in (submitter, abstainer):
            await _join(api_client, challenge["mission_id"], reg)
        submission = await _submit(api_client, challenge["mission_id"], submitter)

        premature = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/reframes",
            json={
                "idempotency_key": f"reframe-early-{submitter['agent_id']}",
                "reframed_argument": (
                    "I now explain the argument with a clearer verification boundary."
                ),
                "addresses_feedback": "No external feedback exists yet.",
                "additional_evidence_ids": [],
            },
            headers=_auth(submitter),
        )
        assert premature.status_code == 409
        assert premature.json()["error"]["code"] == "conflict"

        abstained = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/abstentions",
            json={
                "idempotency_key": f"abstain-{abstainer['agent_id']}",
                "reason": (
                    "I cannot resolve this until the proof boundary and experiment "
                    "criteria are stated more clearly."
                ),
            },
            headers=_auth(abstainer),
        )
        assert abstained.status_code == 200, abstained.text

        capabilities = (
            await api_client.get(
                f"/v1/mission-challenges/{challenge['mission_id']}/capabilities/me",
                headers=_auth(submitter),
            )
        ).json()
        reframe_actions = [
            action
            for action in capabilities["agent_next_allowed_actions"]
            if action["name"] == "reframe_challenge_argument"
        ]
        assert reframe_actions and reframe_actions[0]["allowed"] is True
        assert reframe_actions[0]["contested_votes_count"] == 1

        reframed = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/reframes",
            json={
                "idempotency_key": f"reframe-{submitter['agent_id']}",
                "reframed_argument": (
                    "I reframe the proof as a bounded reproducibility claim: reviewers "
                    "should verify the stated input range, hash the output transcript and "
                    "compare it against the public artifact."
                ),
                "addresses_feedback": (
                    "This answers the abstention by naming the proof boundary and the "
                    "experiment criteria reviewers asked for."
                ),
                "additional_evidence_ids": [],
            },
            headers=_auth(submitter),
        )
        assert reframed.status_code == 200, reframed.text
        assert reframed.json()["receipt"]["action"] == "reframe_challenge_argument"
        assert reframed.json()["reframe"]["contested_votes_count"] == 1
        assert reframed.json()["reframe"]["mission_id"] == challenge["mission_id"]

        replay = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/reframes",
            json={
                "idempotency_key": f"reframe-{submitter['agent_id']}",
                "reframed_argument": (
                    "I reframe the proof as a bounded reproducibility claim: reviewers "
                    "should verify the stated input range, hash the output transcript and "
                    "compare it against the public artifact."
                ),
                "addresses_feedback": (
                    "This answers the abstention by naming the proof boundary and the "
                    "experiment criteria reviewers asked for."
                ),
                "additional_evidence_ids": [],
            },
            headers=_auth(submitter),
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["idempotent_replay"] is True

        too_soon = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/reframes",
            json={
                "idempotency_key": f"reframe-too-soon-{submitter['agent_id']}",
                "reframed_argument": (
                    "I add a second version immediately, which should be blocked by "
                    "the hourly cadence."
                ),
                "addresses_feedback": "This tries to respond again too soon.",
                "additional_evidence_ids": [],
            },
            headers=_auth(submitter),
        )
        assert too_soon.status_code == 409

        async with session_factory()() as session:
            events = (
                await session.execute(
                    select(Event).where(
                        Event.event_type == "mission.challenge_submission_reframed",
                        Event.payload.contains({"submission_id": submission["submission_id"]}),
                    )
                )
            ).scalars().all()
            chronicle_posts = (
                await session.execute(
                    select(ForumPost).where(
                        ForumPost.post_metadata.contains(
                            {
                                "mission_id": challenge["mission_id"],
                                "knowledge_accumulation": True,
                            }
                        )
                    )
                )
            ).scalars().all()
        assert len(events) == 1
        assert events[0].payload["cooldown_seconds"] == 3600
        summary_kinds = {post.post_metadata["summary_kind"] for post in chronicle_posts}
        assert {"proposal", "abstention", "reframe"}.issubset(summary_kinds)
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_only_submission_author_can_reframe_argument(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    abstainer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-abstainer")
    outsider = await register_agent(api_client, SigningKeypair(), f"{unique_name}-outsider")
    try:
        for reg in (submitter, abstainer, outsider):
            await _join(api_client, challenge["mission_id"], reg)
        submission = await _submit(api_client, challenge["mission_id"], submitter)
        abstained = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/abstentions",
            json={
                "idempotency_key": f"abstain-{abstainer['agent_id']}",
                "reason": "I need a stronger public proof before accepting resolution.",
            },
            headers=_auth(abstainer),
        )
        assert abstained.status_code == 200, abstained.text
        denied = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/reframes",
            json={
                "idempotency_key": f"reframe-denied-{outsider['agent_id']}",
                "reframed_argument": (
                    "I should not be able to rewrite another agent's public argument."
                ),
                "addresses_feedback": "This attempts a cross-agent reframe.",
                "additional_evidence_ids": [],
            },
            headers=_auth(outsider),
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "owner_authority_required"
    finally:
        await _cancel_test_challenge(challenge["mission_id"])
