"""Mandatory Sprint 06 E2E: First Championship.

Eight independent synthetic agents enter Arena. The coordinator publishes a
small challenge set, freezes rules before submissions, resolves a
deterministic verifier, records audience preference separately from
correctness, detects same-owner farming and rebuilds leaderboard state from
append-only ScoreEvents.
"""

import pytest
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.models import Agent, User

from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_arena import _challenge_body

pytestmark = pytest.mark.e2e


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _same_owner(*agent_ids: str) -> None:
    async with session_factory()() as session:
        owner = User(
            user_id=f"usr_{agent_ids[0].removeprefix('agt_')[:26]}",
            username=f"championship-owner-{agent_ids[0][-8:]}",
            created_at=now_utc(),
        )
        session.add(owner)
        for agent_id in agent_ids:
            agent = await session.get(Agent, agent_id)
            assert agent is not None
            agent.owner_id = owner.user_id
        await session.commit()


async def _create_open_instance(api_client, creator: dict, body: dict, max_participants: int = 16):
    challenge = (
        await api_client.post("/v1/arena/challenges", json=body, headers=_auth(creator))
    ).json()
    opened = await api_client.post(
        f"/v1/arena/challenges/{challenge['challenge_id']}/open", headers=_auth(creator)
    )
    assert opened.status_code == 200
    instance = await api_client.post(
        f"/v1/arena/challenges/{challenge['challenge_id']}/instances",
        json={"max_participants": max_participants},
        headers=_auth(creator),
    )
    assert instance.status_code == 201, instance.text
    return challenge, instance.json()


async def test_first_championship(api_client, unique_name):
    agents = [
        await register_agent(api_client, SigningKeypair(), f"{unique_name}-arena-{idx}")
        for idx in range(8)
    ]
    coordinator = agents[0]
    competitor_a = agents[1]
    competitor_b = agents[2]
    voter = agents[3]
    farmer_a = agents[4]
    farmer_b = agents[5]
    await _same_owner(farmer_a["agent_id"], farmer_b["agent_id"])

    # Publish a set of deterministic/meta challenges with frozen rules.
    math_challenge, math_instance = await _create_open_instance(
        api_client, coordinator, _challenge_body("42"), max_participants=16
    )
    forecast_body = _challenge_body("UP")
    forecast_body |= {
        "title": "Forecast simulated market direction",
        "kind": "forecasting",
        "domain": "Forecasting",
        "verifier_manifest": {
            "schema_version": "1.0",
            "verifier_type": "simulated_outcome",
            "expected_answer": "UP",
            "tolerance": None,
            "notes": "Outcome is simulated for deterministic Sprint 06 tests.",
        },
    }
    await _create_open_instance(api_client, coordinator, forecast_body, max_participants=16)
    debate_body = _challenge_body("manual")
    debate_body |= {
        "title": "Debate: should popularity imply truth?",
        "kind": "debate",
        "domain": "Debate",
        "verifier_manifest": {
            "schema_version": "1.0",
            "verifier_type": "manual",
            "expected_answer": None,
            "tolerance": None,
            "notes": "DebateMatch metadata reuses Social Intelligence concepts; no truth score.",
        },
    }
    await _create_open_instance(api_client, coordinator, debate_body, max_participants=16)

    iid = math_instance["challenge_instance_id"]
    for reg in (competitor_a, competitor_b, farmer_a, farmer_b):
        joined = await api_client.post(f"/v1/arena/instances/{iid}/join", headers=_auth(reg))
        assert joined.status_code == 201

    # Rules are frozen before submissions.
    detail = (await api_client.get(f"/v1/arena/challenges/{math_challenge['challenge_id']}")).json()
    assert detail["versions"][0]["frozen_at"] is not None
    frozen_formula = detail["versions"][0]["scoring_formula"]

    sub_a = (
        await api_client.post(
            f"/v1/arena/instances/{iid}/submissions",
            json={"answer": "41"},
            headers=_auth(competitor_a),
        )
    ).json()
    sub_b = (
        await api_client.post(
            f"/v1/arena/instances/{iid}/submissions",
            json={"answer": "42"},
            headers=_auth(competitor_b),
        )
    ).json()
    farm_sub = (
        await api_client.post(
            f"/v1/arena/instances/{iid}/submissions",
            json={"answer": "42"},
            headers=_auth(farmer_a),
        )
    ).json()

    # Popular vote favors the wrong answer, but it remains audience preference.
    vote = await api_client.post(
        f"/v1/arena/instances/{iid}/audience-votes",
        json={"preferred_submission_id": sub_a["submission_id"], "clarity": 5},
        headers=_auth(voter),
    )
    assert vote.status_code == 201
    assert vote.json()["correctness"] is None

    judged_wrong = (
        await api_client.post(
            f"/v1/arena/submissions/{sub_a['submission_id']}/judge", headers=_auth(coordinator)
        )
    ).json()
    judged_correct = (
        await api_client.post(
            f"/v1/arena/submissions/{sub_b['submission_id']}/judge", headers=_auth(coordinator)
        )
    ).json()
    judged_farm = (
        await api_client.post(
            f"/v1/arena/submissions/{farm_sub['submission_id']}/judge", headers=_auth(coordinator)
        )
    ).json()

    assert judged_wrong["score_event"]["factors"]["correctness"] == 0.0
    assert judged_correct["score_event"]["factors"]["correctness"] == 1.0
    assert (
        "same_owner_participant_cluster"
        in judged_farm["score_event"]["factors"]["anomaly_flags"]
    )
    assert (
        judged_farm["score_event"]["score_delta"]
        < judged_correct["score_event"]["score_delta"]
    )

    resolved = await api_client.post(
        f"/v1/arena/instances/{iid}/resolve",
        headers=_auth(coordinator),
    )
    assert resolved.status_code == 200

    projection = (await api_client.get("/v1/arena/leaderboard")).json()
    rebuilt = (await api_client.get("/v1/arena/leaderboard/rebuild")).json()
    projected = {row["agent_id"]: row["points"] for row in projection["leaderboard"]}
    rebuilt_points = {row["agent_id"]: row["points"] for row in rebuilt["leaderboard"]}
    assert projected[competitor_b["agent_id"]] == rebuilt_points[competitor_b["agent_id"]]
    assert projection["truth_score"] is None
    assert projection["epistemic_reputation"] is None

    after = (await api_client.get(f"/v1/arena/challenges/{math_challenge['challenge_id']}")).json()
    assert after["versions"][0]["scoring_formula"] == frozen_formula
