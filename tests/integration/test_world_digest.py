"""GET /v1/world/digest: deterministic human-language digest of world facts."""

import pytest

from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_challenge_knowledge_threads import _contribute
from tests.integration.test_mission_challenges import (
    _auth,
    _cancel_test_challenge,
    _join,
    _seed_challenge,
    _seed_evidence,
    _submit,
)

pytestmark = pytest.mark.integration


async def _digest(api_client, window_seconds: int = 1800) -> dict:
    response = await api_client.get(f"/v1/world/digest?window_seconds={window_seconds}")
    assert response.status_code == 200, response.text
    return response.json()


def _pipeline_entry(digest: dict, mission_id: str) -> dict:
    entries = [row for row in digest["pipeline_stages"] if row["mission_id"] == mission_id]
    assert entries, digest["pipeline_stages"]
    return entries[0]


async def test_digest_contract_and_window_bounds(api_client):
    digest = await _digest(api_client)
    assert digest["digest_version"] == "world-digest-v1"
    assert digest["language"] == "es"
    assert digest["generator"] == "deterministic_templates_from_ledger_events_no_llm"
    assert digest["window_seconds"] == 1800
    assert isinstance(digest["facts"], dict)
    assert isinstance(digest["headlines"], list)
    assert digest["headlines"], "the digest always explains the window, even if empty"
    assert digest["truth_contract"]["no_llm_generation"] is True
    stage_percents = [row["percent"] for row in digest["pipeline_stage_order"]]
    assert stage_percents == [0, 10, 25, 45, 60, 75, 90, 100]
    assert all(
        row["validators_enter_at"] == 90 for row in digest["pipeline_stages"]
    )

    too_large = await api_client.get("/v1/world/digest?window_seconds=999999")
    assert too_large.status_code == 422


async def test_digest_counts_headlines_and_pipeline_progression(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-digest-voter")
    mission_id = challenge["mission_id"]
    try:
        await _join(api_client, mission_id, submitter)
        await _join(api_client, mission_id, voter)

        joined = _pipeline_entry(await _digest(api_client), mission_id)
        assert joined["stage"] == "joined"
        assert joined["percent"] == 10
        assert joined["counts"]["participants"] == 2

        submission = await _submit(api_client, mission_id, submitter)

        submitted = _pipeline_entry(await _digest(api_client), mission_id)
        assert submitted["stage"] == "submitted"
        assert submitted["percent"] == 45
        assert submitted["counts"]["submissions"] == 1

        review_evidence_id = await _seed_evidence(f"{unique_name}-review", voter)
        vote = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
            json={
                "idempotency_key": f"vote-{voter['agent_id']}",
                "verdict": "not_resolved",
                "review_evidence_ids": [review_evidence_id],
                "public_rationale": (
                    "The public argument does not yet include decisive primary evidence."
                ),
                "conflict_of_interest_declaration": "none",
            },
            headers=_auth(voter),
        )
        assert vote.status_code == 200, vote.text

        digest = await _digest(api_client)
        under_review = _pipeline_entry(digest, mission_id)
        assert under_review["stage"] == "under_review"
        assert under_review["percent"] == 75
        assert under_review["counts"]["votes"] == 1
        assert under_review["validators_enter_at"] == 90

        facts = digest["facts"]
        assert facts["submissions_finalized"] >= 1
        assert facts["votes"] >= 1
        assert facts["votes_by_verdict"].get("not_resolved", 0) >= 1

        # Tight window for headline assertions too: MAX_HEADLINES caps the
        # list, and on a shared CI database the default window can carry more
        # than 16 newer headlines from surrounding tests.
        digest = await _digest(api_client, window_seconds=120)
        headlines = " || ".join(digest["headlines"])
        submitter_name = f"{unique_name}-creator"
        voter_name = f"{unique_name}-digest-voter"
        assert (
            f"{submitter_name} publicó una solución al reto «Challenge {unique_name}»"
            in headlines
        ), headlines
        vote_headlines = [
            line
            for line in digest["headlines"]
            if voter_name in line and "NO RESUELTO" in line
        ]
        assert vote_headlines, digest["headlines"]
        assert submitter_name in vote_headlines[0]
        assert "con evidencia" in vote_headlines[0]

        # Tight window: on a shared CI database the default window can hold
        # more than MAX_PER_AGENT busier agents from earlier tests; the events
        # of THIS test are the newest, so a 120s window isolates them.
        fresh = await _digest(api_client, window_seconds=120)
        per_agent = {row["name"]: row for row in fresh["per_agent"]}
        assert per_agent[submitter_name]["counts"]["publish"] >= 1
        assert per_agent[voter_name]["counts"]["review"] >= 1
        assert per_agent[voter_name]["counts"]["evidence"] >= 1
        assert per_agent[voter_name]["counts"]["consistency_buckets"] >= 1
    finally:
        await _cancel_test_challenge(mission_id)


async def test_digest_thread_contributions_reach_thread_developing_stage(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    peer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-digest-peer")
    mission_id = challenge["mission_id"]
    try:
        await _join(api_client, mission_id, submitter)
        await _join(api_client, mission_id, peer)
        submission = await _submit(api_client, mission_id, submitter)

        contribution = await _contribute(
            api_client,
            submission["submission_id"],
            peer,
            kind="critique",
            body=(
                "Public critique: the bounded experiment range should also report "
                "the failure modes it excluded."
            ),
        )
        assert contribution.status_code == 201, contribution.text

        digest = await _digest(api_client)
        entry = _pipeline_entry(digest, mission_id)
        assert entry["stage"] == "thread_developing"
        assert entry["percent"] == 60
        assert entry["counts"]["thread_contributions"] == 1

        assert digest["facts"]["thread_contributions"] >= 1
        assert digest["facts"]["thread_contributions_by_kind"].get("critique", 0) >= 1

        peer_name = f"{unique_name}-digest-peer"
        thread_headlines = [
            line
            for line in digest["headlines"]
            if peer_name in line and "hilo de conocimiento" in line
        ]
        assert thread_headlines, digest["headlines"]
        assert f"«Challenge {unique_name}»" in thread_headlines[0]
        assert "crítica" in thread_headlines[0]
    finally:
        await _cancel_test_challenge(mission_id)
