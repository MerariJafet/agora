"""Debate lifecycle, participant concurrency, audience assessment
(S4-T09/T10/T11/T12, S4-T20)."""

import asyncio
import secrets

import pytest
from agora_api.db import session_factory
from sqlalchemy import select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration

PLAZA = "spc_00000000000000000000P1AZA0"


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _create_debate(api_client, reg: dict, max_participants: int = 2) -> dict:
    r = await api_client.post(
        f"/v1/spaces/{PLAZA}/debates",
        json={"question": "Is X true?", "positions": ["YES", "NO"],
              "max_participants": max_participants},
        headers=_auth(reg),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_open_join_two_participants(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    debate = await _create_debate(api_client, a)
    assert debate["status"] == "open"
    assert len(debate["positions"]) == 2

    join_a = await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(a))
    assert join_a.status_code == 201
    join_b = await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(b))
    assert join_b.status_code == 201

    detail = (await api_client.get(f"/v1/debates/{debate['debate_id']}")).json()
    assert {p["agent_id"] for p in detail["participants"]} == {a["agent_id"], b["agent_id"]}


async def test_third_participant_rejected_when_full(api_client, unique_name):
    kp_a, kp_b, kp_c = SigningKeypair(), SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    c = await register_agent(api_client, kp_c, f"{unique_name}-C")
    debate = await _create_debate(api_client, a, max_participants=2)
    await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(a))
    await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(b))
    third = await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(c))
    assert third.status_code == 409
    assert third.json()["error"]["code"] == "debate_full"


async def test_concurrent_join_race_for_last_slot(api_client, unique_name):
    """Two agents race for the final slot of a 2-person debate; exactly one
    must win (S4-T10)."""
    kp_a, kp_b, kp_c = SigningKeypair(), SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    c = await register_agent(api_client, kp_c, f"{unique_name}-C")
    debate = await _create_debate(api_client, a, max_participants=2)
    await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(a))

    results = await asyncio.gather(
        api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(b)),
        api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(c)),
        return_exceptions=True,
    )
    statuses = sorted(r.status_code for r in results if not isinstance(r, Exception))
    assert statuses == [201, 409]

    async with session_factory()() as session:
        from agora_api.models import DebateParticipant

        rows = (
            await session.execute(
                select(DebateParticipant).where(
                    DebateParticipant.debate_id == debate["debate_id"],
                    DebateParticipant.left_at.is_(None),
                )
            )
        ).scalars().all()
        assert len(rows) == 2  # never 3


async def test_larger_configurable_limit(api_client, unique_name):
    a = await register_agent(api_client, SigningKeypair(), f"{unique_name}-lead")
    debate = await _create_debate(api_client, a, max_participants=6)
    for i in range(6):
        reg = await register_agent(api_client, SigningKeypair(), f"{unique_name}-p{i}")
        r = await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(reg))
        assert r.status_code == 201
    overflow = await register_agent(api_client, SigningKeypair(), f"{unique_name}-overflow")
    r = await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(overflow))
    assert r.status_code == 409


async def test_max_participants_out_of_range_rejected(api_client, unique_name):
    a = await register_agent(api_client, SigningKeypair(), unique_name)
    r = await api_client.post(
        f"/v1/spaces/{PLAZA}/debates",
        json={"question": "x?", "positions": ["A", "B"], "max_participants": 1},
        headers=_auth(a),
    )
    assert r.status_code == 422


async def test_set_position_requires_participation(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    debate = await _create_debate(api_client, a)
    await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(a))
    yes_position = debate["positions"][0]["position_id"]

    not_joined = await api_client.post(
        f"/v1/debates/{debate['debate_id']}/position",
        json={"position_id": yes_position}, headers=_auth(b),
    )
    assert not_joined.status_code == 403

    joined = await api_client.post(
        f"/v1/debates/{debate['debate_id']}/position",
        json={"position_id": yes_position}, headers=_auth(a),
    )
    assert joined.status_code == 200
    assert joined.json()["position_id"] == yes_position


async def test_position_change_is_auditable(api_client, unique_name):
    a = await register_agent(api_client, SigningKeypair(), unique_name)
    debate = await _create_debate(api_client, a)
    await api_client.post(f"/v1/debates/{debate['debate_id']}/join", headers=_auth(a))
    yes, no = debate["positions"][0]["position_id"], debate["positions"][1]["position_id"]
    await api_client.post(f"/v1/debates/{debate['debate_id']}/position",
                          json={"position_id": yes}, headers=_auth(a))
    await api_client.post(f"/v1/debates/{debate['debate_id']}/position",
                          json={"position_id": no}, headers=_auth(a))
    async with session_factory()() as session:
        from agora_api.models import Event

        events = (
            await session.execute(
                select(Event).where(
                    Event.event_type == "debate.position_changed",
                    Event.payload["debate_id"].astext == debate["debate_id"],
                )
            )
        ).scalars().all()
    assert len(events) == 2


async def test_agent_audience_assessment_upsert_and_freeze(api_client, unique_name):
    kp_a, kp_spec = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    spectator = await register_agent(api_client, kp_spec, f"{unique_name}-spec")
    debate = await _create_debate(api_client, a)
    pos = debate["positions"][0]["position_id"]

    first = await api_client.put(
        f"/v1/debates/{debate['debate_id']}/assessment/agent",
        json={"preferred_position_id": pos, "evidence_quality": 4, "clarity": 3},
        headers=_auth(spectator),
    )
    assert first.status_code == 200
    updated = await api_client.put(
        f"/v1/debates/{debate['debate_id']}/assessment/agent",
        json={"preferred_position_id": pos, "evidence_quality": 5, "clarity": 5},
        headers=_auth(spectator),
    )
    assert updated.status_code == 200

    summary = (await api_client.get(f"/v1/debates/{debate['debate_id']}/assessment-summary")).json()
    assert summary["agent_audience_perception"]["count"] == 1  # upsert, not duplicate
    assert summary["agent_audience_perception"]["avg_evidence_quality"] == 5
    disclaimer = summary["disclaimer"]
    assert "not verified factual truth" in disclaimer or "not truth" in disclaimer

    close = await api_client.post(f"/v1/debates/{debate['debate_id']}/close", headers=_auth(a))
    assert close.status_code == 200

    frozen = await api_client.put(
        f"/v1/debates/{debate['debate_id']}/assessment/agent",
        json={"preferred_position_id": pos, "evidence_quality": 1}, headers=_auth(spectator),
    )
    assert frozen.status_code == 409
    assert frozen.json()["error"]["code"] == "debate_closed"


async def test_only_creator_can_close_debate(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    debate = await _create_debate(api_client, a)
    denied = await api_client.post(f"/v1/debates/{debate['debate_id']}/close", headers=_auth(b))
    assert denied.status_code == 403


async def test_human_assessment_requires_csrf(api_client, unique_name):
    a = await register_agent(api_client, SigningKeypair(), unique_name)
    debate = await _create_debate(api_client, a)
    login = await api_client.post(
        "/v1/auth/dev/login", json={"username": f"assessor-{secrets.token_hex(4)}"}
    )
    no_csrf = await api_client.put(
        f"/v1/debates/{debate['debate_id']}/assessment/human",
        json={"evidence_quality": 3},
    )
    assert no_csrf.status_code == 403
    with_csrf = await api_client.put(
        f"/v1/debates/{debate['debate_id']}/assessment/human",
        json={"evidence_quality": 3},
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert with_csrf.status_code == 200


async def test_human_and_agent_perception_kept_separate(api_client, unique_name):
    a = await register_agent(api_client, SigningKeypair(), unique_name)
    agent_spectator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-spec")
    debate = await _create_debate(api_client, a)
    login = await api_client.post(
        "/v1/auth/dev/login", json={"username": f"human-{secrets.token_hex(4)}"}
    )
    await api_client.put(
        f"/v1/debates/{debate['debate_id']}/assessment/human",
        json={"evidence_quality": 2},
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
    )
    await api_client.put(
        f"/v1/debates/{debate['debate_id']}/assessment/agent",
        json={"evidence_quality": 5}, headers=_auth(agent_spectator),
    )
    summary = (await api_client.get(f"/v1/debates/{debate['debate_id']}/assessment-summary")).json()
    assert summary["human_audience_perception"]["avg_evidence_quality"] == 2
    assert summary["agent_audience_perception"]["avg_evidence_quality"] == 5


async def _claim(api_client, reg: dict, keypair: SigningKeypair, username: str) -> None:
    login = await api_client.post("/v1/auth/dev/login", json={"username": username})
    csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
    claim = await api_client.post(
        "/v1/owner/claims", json={"agent_id": reg["agent_id"]}, headers=csrf
    )
    code = claim.json()["claim_code"]
    signature = keypair.sign_b64(f"agora.claim.v1|{reg['agent_id']}|{code}".encode())
    consumed = await api_client.post(
        "/v1/registration/claim",
        json={"agent_id": reg["agent_id"], "code": code,
              "device_id": reg["device_id"], "signature": signature},
    )
    assert consumed.status_code == 200, consumed.text


async def test_owner_normalized_agent_perception(api_client, unique_name):
    """Two agents owned by the SAME owner average to one voice; an
    independently-owned agent counts as its own voice."""
    creator = await register_agent(api_client, SigningKeypair(), f"{unique_name}-creator")
    debate = await _create_debate(api_client, creator)

    owner_name = f"owner-{secrets.token_hex(4)}"
    kp_1, kp_2, kp_ind = SigningKeypair(), SigningKeypair(), SigningKeypair()
    same_owner_1 = await register_agent(api_client, kp_1, f"{unique_name}-so1")
    same_owner_2 = await register_agent(api_client, kp_2, f"{unique_name}-so2")
    independent = await register_agent(api_client, kp_ind, f"{unique_name}-ind")

    await _claim(api_client, same_owner_1, kp_1, owner_name)
    await _claim(api_client, same_owner_2, kp_2, owner_name)
    await _claim(api_client, independent, kp_ind, f"indie-{secrets.token_hex(4)}")

    # same owner's two agents both vote high; independent agent votes low
    await api_client.put(f"/v1/debates/{debate['debate_id']}/assessment/agent",
                         json={"evidence_quality": 5}, headers=_auth(same_owner_1))
    await api_client.put(f"/v1/debates/{debate['debate_id']}/assessment/agent",
                         json={"evidence_quality": 5}, headers=_auth(same_owner_2))
    await api_client.put(f"/v1/debates/{debate['debate_id']}/assessment/agent",
                         json={"evidence_quality": 1}, headers=_auth(independent))

    summary = (await api_client.get(f"/v1/debates/{debate['debate_id']}/assessment-summary")).json()
    # raw agent average would be (5+5+1)/3 ≈ 3.67; owner-normalized is (5+1)/2 = 3
    assert summary["agent_audience_perception"]["avg_evidence_quality"] > 3.5
    normalized = summary["owner_normalized_agent_perception"]
    assert normalized is not None
    assert normalized["distinct_owners"] == 2
    assert normalized["avg_evidence_quality"] == 3.0


async def test_no_truth_score_or_winner_anywhere(api_client, unique_name):
    """The API surface for a debate never produces a winner or a numeric
    truth score — only descriptive perception aggregates."""
    a = await register_agent(api_client, SigningKeypair(), unique_name)
    debate = await _create_debate(api_client, a)
    closed = await api_client.post(f"/v1/debates/{debate['debate_id']}/close", headers=_auth(a))
    body = closed.json()
    for forbidden_key in ("winner", "truth_score", "truth_probability", "arena_points", "elo"):
        assert forbidden_key not in body
    summary = (await api_client.get(f"/v1/debates/{debate['debate_id']}/assessment-summary")).json()
    for forbidden_key in ("winner", "truth_score", "truth_probability", "arena_points", "elo"):
        assert forbidden_key not in summary
