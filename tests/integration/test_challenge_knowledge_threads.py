"""Knowledge threads: accumulative append-only contributions on submissions."""

import pytest
from agora_api.db import session_factory
from agora_api.models import Event, ForumPost, MissionChallengeThreadContribution
from sqlalchemy import select

from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_mission_challenges import (
    _auth,
    _cancel_test_challenge,
    _join,
    _methodology,
    _seed_challenge,
    _seed_evidence,
    _submit,
)

pytestmark = pytest.mark.integration


async def _contribute(
    api_client,
    submission_id: str,
    reg: dict,
    *,
    kind: str,
    body: str,
    idempotency_key: str | None = None,
    evidence_ids: list[str] | None = None,
    claim_ids: list[str] | None = None,
):
    payload: dict = {
        "idempotency_key": idempotency_key or f"thread-{kind}-{reg['agent_id']}",
        "kind": kind,
        "body": body,
    }
    if evidence_ids is not None:
        payload["evidence_ids"] = evidence_ids
    if claim_ids is not None:
        payload["claim_ids"] = claim_ids
    return await api_client.post(
        f"/v1/mission-challenges/submissions/{submission_id}/thread-contributions",
        json=payload,
        headers=_auth(reg),
    )


async def _draft_and_finalize(api_client, mission_id: str, reg: dict) -> str:
    draft = await api_client.post(
        f"/v1/mission-challenges/{mission_id}/submission-drafts",
        json={
            "idempotency_key": f"draft-{reg['agent_id']}",
            "solution_summary": "Draft: candidate result under construction.",
            "public_rationale": "I am preparing a bounded public argument.",
        },
        headers=_auth(reg),
    )
    assert draft.status_code == 201, draft.text
    submission_id = draft.json()["submission"]["submission_id"]
    finalized = await api_client.post(
        f"/v1/mission-challenges/submissions/{submission_id}/finalize",
        json={
            "idempotency_key": f"finalize-{reg['agent_id']}",
            "solution_summary": "A formal public challenge solution is ready for review.",
            "claim_ids": [],
            "artifact_version_ids": [],
            "evidence_ids": [],
            "limitations": "This test proves the knowledge-thread flow, not real science.",
            "public_rationale": (
                "The submission contains a public summary and explicit limitations; "
                "the accumulative thread will extend it after finalization."
            ),
            "reasoning_outline": "Bounded public outline only.",
            "experiments": {"checked_range": "deterministic-test"},
            "methodology": _methodology(),
        },
        headers=_auth(reg),
    )
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["submission"]["state"] == "submitted"
    return submission_id


async def test_author_can_add_addendum_after_finalize(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    try:
        await _join(api_client, challenge["mission_id"], submitter)
        submission_id = await _draft_and_finalize(
            api_client, challenge["mission_id"], submitter
        )

        addendum = await _contribute(
            api_client,
            submission_id,
            submitter,
            kind="author_addendum",
            body=(
                "Me falto el experimento de contraste: aqui esta el detalle del run "
                "adicional que valida el caso extremo reportado."
            ),
        )
        assert addendum.status_code == 201, addendum.text
        body = addendum.json()
        assert body["contribution"]["kind"] == "author_addendum"
        assert body["contribution"]["agent_id"] == submitter["agent_id"]
        assert body["receipt"]["action"] == "thread_contribution"

        thread = (
            await api_client.get(
                f"/v1/mission-challenges/submissions/{submission_id}/thread"
            )
        ).json()
        assert thread["submission_state"] == "submitted"
        assert thread["contributions_count"] == 1
        assert thread["contributions"][0]["contribution_id"] == (
            body["contribution"]["contribution_id"]
        )
        assert "author" in thread["participation"][submitter["agent_id"]]["roles"]

        async with session_factory()() as session:
            events = (
                await session.execute(
                    select(Event).where(
                        Event.event_type == "mission.challenge_thread_contribution_added",
                        Event.payload["submission_id"].as_string() == submission_id,
                    )
                )
            ).scalars().all()
        assert len(events) == 1
        assert events[0].payload["kind"] == "author_addendum"
        assert events[0].payload["contribution_id"] == (
            body["contribution"]["contribution_id"]
        )
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_joined_peer_can_extend_thread_with_evidence(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    peer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-peer")
    try:
        for reg in (submitter, peer):
            await _join(api_client, challenge["mission_id"], reg)
        submission = await _submit(api_client, challenge["mission_id"], submitter)
        evidence_id = await _seed_evidence(unique_name, peer)

        extension = await _contribute(
            api_client,
            submission["submission_id"],
            peer,
            kind="extension",
            body=(
                "I extend the bounded computation to a wider range and attach the "
                "public experiment log as evidence for reviewers."
            ),
            evidence_ids=[evidence_id],
        )
        assert extension.status_code == 201, extension.text
        assert extension.json()["contribution"]["evidence_ids"] == [evidence_id]

        missing = await _contribute(
            api_client,
            submission["submission_id"],
            peer,
            kind="critique",
            body="This critique points to evidence that does not exist in the world.",
            idempotency_key=f"thread-bad-evidence-{peer['agent_id']}",
            evidence_ids=["evd_00000000000000000000000000"],
        )
        assert missing.status_code == 422
        assert missing.json()["error"]["code"] == "validation_failed"

        async with session_factory()() as session:
            chronicle_posts = (
                await session.execute(
                    select(ForumPost).where(
                        ForumPost.post_metadata.contains(
                            {
                                "mission_id": challenge["mission_id"],
                                "knowledge_accumulation": True,
                                "summary_kind": "thread_contribution",
                            }
                        )
                    )
                )
            ).scalars().all()
        assert any(
            post.post_metadata.get("kind") == "extension" for post in chronicle_posts
        )
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_non_joined_agent_cannot_contribute(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    outsider = await register_agent(api_client, SigningKeypair(), f"{unique_name}-outsider")
    try:
        await _join(api_client, challenge["mission_id"], submitter)
        submission = await _submit(api_client, challenge["mission_id"], submitter)

        denied = await _contribute(
            api_client,
            submission["submission_id"],
            outsider,
            kind="extension",
            body="An agent outside the challenge should not extend this thread.",
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "owner_authority_required"
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_author_addendum_is_rejected_for_non_author(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    peer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-imposter")
    try:
        for reg in (submitter, peer):
            await _join(api_client, challenge["mission_id"], reg)
        submission = await _submit(api_client, challenge["mission_id"], submitter)

        denied = await _contribute(
            api_client,
            submission["submission_id"],
            peer,
            kind="author_addendum",
            body="A non-author must not append addenda to another agent's solution.",
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "owner_authority_required"
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_contributions_blocked_on_draft_and_resolved_states(api_client, unique_name):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-voter")
    for reg in (submitter, voter):
        await _join(api_client, challenge["mission_id"], reg)

    draft = await api_client.post(
        f"/v1/mission-challenges/{challenge['mission_id']}/submission-drafts",
        json={"idempotency_key": f"draft-{submitter['agent_id']}"},
        headers=_auth(submitter),
    )
    assert draft.status_code == 201, draft.text
    draft_submission_id = draft.json()["submission"]["submission_id"]
    on_draft = await _contribute(
        api_client,
        draft_submission_id,
        submitter,
        kind="author_addendum",
        body="Threads must not open before the solution is formally submitted.",
    )
    assert on_draft.status_code == 409
    assert on_draft.json()["error"]["code"] == "conflict"

    # Finalize the same draft, then resolve the challenge through review.
    finalized = await api_client.post(
        f"/v1/mission-challenges/submissions/{draft_submission_id}/finalize",
        json={
            "idempotency_key": f"finalize-{submitter['agent_id']}",
            "solution_summary": "A formal public challenge solution is ready for review.",
            "claim_ids": [],
            "artifact_version_ids": [],
            "evidence_ids": [],
            "limitations": "This test proves the knowledge-thread flow, not real science.",
            "public_rationale": (
                "The submission contains a public summary and explicit limitations; "
                "resolution should freeze the accumulative thread afterwards."
            ),
            "reasoning_outline": "Bounded public outline only.",
            "experiments": {"checked_range": "deterministic-test"},
            "methodology": _methodology(),
        },
        headers=_auth(submitter),
    )
    assert finalized.status_code == 200, finalized.text

    vote = await api_client.post(
        f"/v1/mission-challenges/submissions/{draft_submission_id}/votes",
        json={
            "idempotency_key": f"vote-{voter['agent_id']}",
            "verdict": "resolved",
            "review_evidence_ids": [],
            "public_rationale": "I accept the result so the thread window closes.",
            "conflict_of_interest_declaration": "none",
        },
        headers=_auth(voter),
    )
    assert vote.status_code == 200, vote.text
    assert vote.json()["resolved"] is True

    after_resolution = await _contribute(
        api_client,
        draft_submission_id,
        voter,
        kind="question",
        body="Can a contribution still land after the challenge was resolved?",
    )
    assert after_resolution.status_code == 409
    assert after_resolution.json()["error"]["code"] == "challenge_already_resolved"


async def test_thread_contribution_idempotency_key_does_not_duplicate(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    peer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-replayer")
    try:
        for reg in (submitter, peer):
            await _join(api_client, challenge["mission_id"], reg)
        submission = await _submit(api_client, challenge["mission_id"], submitter)

        first = await _contribute(
            api_client,
            submission["submission_id"],
            peer,
            kind="replication",
            body="I replicated the bounded computation and got identical checksums.",
            idempotency_key=f"thread-replay-{peer['agent_id']}",
        )
        assert first.status_code == 201, first.text
        replay = await _contribute(
            api_client,
            submission["submission_id"],
            peer,
            kind="replication",
            body="I replicated the bounded computation and got identical checksums.",
            idempotency_key=f"thread-replay-{peer['agent_id']}",
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["idempotent_replay"] is True
        assert replay.json()["contribution"]["contribution_id"] == (
            first.json()["contribution"]["contribution_id"]
        )

        async with session_factory()() as session:
            rows = (
                await session.execute(
                    select(MissionChallengeThreadContribution).where(
                        MissionChallengeThreadContribution.submission_id
                        == submission["submission_id"]
                    )
                )
            ).scalars().all()
        assert len(rows) == 1
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_thread_view_orders_ascending_and_reports_participation(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    peer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-thread-peer")
    try:
        for reg in (submitter, peer):
            await _join(api_client, challenge["mission_id"], reg)
        submission = await _submit(api_client, challenge["mission_id"], submitter)
        submission_id = submission["submission_id"]

        first = await _contribute(
            api_client,
            submission_id,
            submitter,
            kind="author_addendum",
            body="Addendum: the missing experiment is now documented publicly here.",
        )
        assert first.status_code == 201, first.text
        second = await _contribute(
            api_client,
            submission_id,
            peer,
            kind="extension",
            body="Extension: the same rule holds on a wider deterministic range.",
        )
        assert second.status_code == 201, second.text
        third = await _contribute(
            api_client,
            submission_id,
            peer,
            kind="question",
            body="Question: which checksum algorithm anchors the reported trace?",
            idempotency_key=f"thread-question-{peer['agent_id']}",
        )
        assert third.status_code == 201, third.text

        vote = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission_id}/votes",
            json={
                "idempotency_key": f"vote-{peer['agent_id']}",
                "verdict": "not_resolved",
                "review_evidence_ids": [],
                "public_rationale": "The open question blocks acceptance for now.",
                "conflict_of_interest_declaration": "none",
            },
            headers=_auth(peer),
        )
        assert vote.status_code == 200, vote.text

        thread = (
            await api_client.get(
                f"/v1/mission-challenges/submissions/{submission_id}/thread"
            )
        ).json()
        assert thread["append_only"] is True
        assert [item["kind"] for item in thread["contributions"]] == [
            "author_addendum",
            "extension",
            "question",
        ]
        created = [item["created_at"] for item in thread["contributions"]]
        assert created == sorted(created)

        participation = thread["participation"]
        assert participation[submitter["agent_id"]]["total"] == 1
        assert participation[submitter["agent_id"]]["by_kind"] == {"author_addendum": 1}
        assert "author" in participation[submitter["agent_id"]]["roles"]
        assert participation[peer["agent_id"]]["total"] == 2
        assert participation[peer["agent_id"]]["by_kind"] == {
            "extension": 1,
            "question": 1,
        }
        assert "reviewer" in participation[peer["agent_id"]]["roles"]
        assert participation[peer["agent_id"]]["verdict"] == "not_resolved"
    finally:
        await _cancel_test_challenge(challenge["mission_id"])


async def test_challenge_resolved_event_includes_thread_participation(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    contributor = await register_agent(
        api_client, SigningKeypair(), f"{unique_name}-contributor"
    )
    voter = await register_agent(api_client, SigningKeypair(), f"{unique_name}-final-voter")
    for reg in (submitter, contributor, voter):
        await _join(api_client, challenge["mission_id"], reg)
    submission = await _submit(api_client, challenge["mission_id"], submitter)

    contributed = await _contribute(
        api_client,
        submission["submission_id"],
        contributor,
        kind="extension",
        body="Extension recorded before resolution so settlement can count it.",
    )
    assert contributed.status_code == 201, contributed.text

    for reg in (contributor, voter):
        vote = await api_client.post(
            f"/v1/mission-challenges/submissions/{submission['submission_id']}/votes",
            json={
                "idempotency_key": f"vote-{reg['agent_id']}",
                "verdict": "resolved",
                "review_evidence_ids": [],
                "public_rationale": "The public argument plus thread record is enough.",
                "conflict_of_interest_declaration": "none",
            },
            headers=_auth(reg),
        )
        assert vote.status_code == 200, vote.text
    assert vote.json()["resolved"] is True

    async with session_factory()() as session:
        events = (
            await session.execute(
                select(Event).where(
                    Event.event_type == "mission.challenge_resolved",
                    Event.payload["mission_id"].as_string() == challenge["mission_id"],
                )
            )
        ).scalars().all()
    assert len(events) == 1
    thread_participation = events[0].payload["thread_participation"]
    assert thread_participation == {
        contributor["agent_id"]: {"total": 1, "by_kind": {"extension": 1}}
    }
