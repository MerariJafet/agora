"""Sprint 06 Arena: immutable challenge rules, deterministic judging,
anti-farming and leaderboard rebuild."""

import pytest
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.models import Agent, User

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


def _challenge_body(expected: str = "42") -> dict:
    return {
        "title": "Answer the calibration problem",
        "description": "Return the known answer.",
        "kind": "math",
        "domain": "Math",
        "complexity": {
            "reasoning": 2,
            "computation": 1,
            "data": 1,
            "domain_expertise": 2,
            "uncertainty": 1,
            "adversariality": 1,
            "verification_cost": 1,
            "time_budget": 1,
        },
        "verifier_manifest": {
            "schema_version": "1.0",
            "verifier_type": "exact_text",
            "expected_answer": expected,
            "tolerance": None,
            "notes": None,
        },
        "scoring_formula": {
            "schema_version": "1.0",
            "base_points": 100,
            "difficulty_weight": 1,
            "opponent_weight": 0,
            "validation_weight": 1,
            "anti_farming_weight": 1,
        },
    }


async def _register(api_client, unique_name: str, suffix: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-{suffix}")


async def _set_same_owner(agent_ids: list[str]) -> None:
    async with session_factory()() as session:
        owner = User(
            user_id=f"usr_{agent_ids[0].removeprefix('agt_')[:26]}",
            username=f"arena-owner-{agent_ids[0][-8:]}",
            created_at=now_utc(),
        )
        session.add(owner)
        for agent_id in agent_ids:
            agent = await session.get(Agent, agent_id)
            assert agent is not None
            agent.owner_id = owner.user_id
        await session.commit()


async def test_challenge_version_freezes_when_instance_starts(api_client, unique_name):
    creator = await _register(api_client, unique_name, "creator")
    created = await api_client.post(
        "/v1/arena/challenges", json=_challenge_body(), headers=_auth(creator)
    )
    assert created.status_code == 201, created.text
    challenge = created.json()
    version_id = challenge["version"]["challenge_version_id"]

    opened = await api_client.post(
        f"/v1/arena/challenges/{challenge['challenge_id']}/open", headers=_auth(creator)
    )
    assert opened.status_code == 200
    instance = await api_client.post(
        f"/v1/arena/challenges/{challenge['challenge_id']}/instances",
        json={"max_participants": 4},
        headers=_auth(creator),
    )
    assert instance.status_code == 201, instance.text

    detail = (await api_client.get(f"/v1/arena/challenges/{challenge['challenge_id']}")).json()
    frozen = detail["versions"][0]
    assert frozen["challenge_version_id"] == version_id
    assert frozen["frozen_at"] is not None
    assert detail["state"] == "active"


async def test_deterministic_verifier_creates_score_event_not_truth(api_client, unique_name):
    creator = await _register(api_client, unique_name, "creator")
    worker = await _register(api_client, unique_name, "worker")
    challenge = (
        await api_client.post(
            "/v1/arena/challenges",
            json=_challenge_body(),
            headers=_auth(creator),
        )
    ).json()
    await api_client.post(f"/v1/arena/challenges/{challenge['challenge_id']}/open",
                          headers=_auth(creator))
    instance = (
        await api_client.post(
            f"/v1/arena/challenges/{challenge['challenge_id']}/instances",
            json={"max_participants": 4}, headers=_auth(creator),
        )
    ).json()
    await api_client.post(
        f"/v1/arena/instances/{instance['challenge_instance_id']}/join", headers=_auth(worker)
    )
    submission = (
        await api_client.post(
            f"/v1/arena/instances/{instance['challenge_instance_id']}/submissions",
            json={"answer": "42"}, headers=_auth(worker),
        )
    ).json()
    judged = await api_client.post(
        f"/v1/arena/submissions/{submission['submission_id']}/judge", headers=_auth(creator)
    )
    assert judged.status_code == 200, judged.text
    score = judged.json()["score_event"]
    assert score["score_delta"] > 0
    assert score["factors"]["correctness"] == 1.0
    assert score["factors"]["truth_claim"] is False
    assert score["factors"]["epistemic_reputation_change"] == 0


async def test_owner_normalized_anti_farming_marks_same_owner_cluster(api_client, unique_name):
    creator = await _register(api_client, unique_name, "creator")
    a = await _register(api_client, unique_name, "same-owner-a")
    b = await _register(api_client, unique_name, "same-owner-b")
    await _set_same_owner([a["agent_id"], b["agent_id"]])

    challenge = (
        await api_client.post(
            "/v1/arena/challenges",
            json=_challenge_body(),
            headers=_auth(creator),
        )
    ).json()
    await api_client.post(f"/v1/arena/challenges/{challenge['challenge_id']}/open",
                          headers=_auth(creator))
    instance = (
        await api_client.post(
            f"/v1/arena/challenges/{challenge['challenge_id']}/instances",
            json={"max_participants": 4}, headers=_auth(creator),
        )
    ).json()
    iid = instance["challenge_instance_id"]
    for reg in (a, b):
        assert (await api_client.post(f"/v1/arena/instances/{iid}/join",
                                      headers=_auth(reg))).status_code == 201
    submission = (
        await api_client.post(
            f"/v1/arena/instances/{iid}/submissions", json={"answer": "42"}, headers=_auth(a)
        )
    ).json()
    judged = (
        await api_client.post(
            f"/v1/arena/submissions/{submission['submission_id']}/judge", headers=_auth(creator)
        )
    ).json()
    factors = judged["score_event"]["factors"]
    assert factors["anti_farming_multiplier"] == 0.5
    assert "same_owner_participant_cluster" in factors["anomaly_flags"]


async def test_audience_vote_is_not_correctness_and_leaderboard_rebuild_matches(
    api_client,
    unique_name,
):
    creator = await _register(api_client, unique_name, "creator")
    worker = await _register(api_client, unique_name, "worker")
    voter = await _register(api_client, unique_name, "voter")
    challenge = (
        await api_client.post(
            "/v1/arena/challenges",
            json=_challenge_body(),
            headers=_auth(creator),
        )
    ).json()
    await api_client.post(f"/v1/arena/challenges/{challenge['challenge_id']}/open",
                          headers=_auth(creator))
    instance = (
        await api_client.post(
            f"/v1/arena/challenges/{challenge['challenge_id']}/instances",
            json={"max_participants": 4}, headers=_auth(creator),
        )
    ).json()
    iid = instance["challenge_instance_id"]
    await api_client.post(f"/v1/arena/instances/{iid}/join", headers=_auth(worker))
    submission = (
        await api_client.post(f"/v1/arena/instances/{iid}/submissions",
                              json={"answer": "42"}, headers=_auth(worker))
    ).json()
    vote = await api_client.post(
        f"/v1/arena/instances/{iid}/audience-votes",
        json={"preferred_submission_id": submission["submission_id"], "clarity": 5},
        headers=_auth(voter),
    )
    assert vote.status_code == 201
    assert vote.json()["correctness"] is None
    await api_client.post(f"/v1/arena/submissions/{submission['submission_id']}/judge",
                          headers=_auth(creator))
    await api_client.post(f"/v1/arena/instances/{iid}/resolve", headers=_auth(creator))
    projection = (await api_client.get("/v1/arena/leaderboard")).json()["leaderboard"]
    rebuilt = (await api_client.get("/v1/arena/leaderboard/rebuild")).json()["leaderboard"]
    projected_worker = next(row for row in projection if row["agent_id"] == worker["agent_id"])
    rebuilt_worker = next(row for row in rebuilt if row["agent_id"] == worker["agent_id"])
    assert projected_worker["points"] == rebuilt_worker["points"]
    assert projected_worker["truth_score"] is None
    assert projected_worker["epistemic_reputation"] is None
