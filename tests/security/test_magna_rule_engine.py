import asyncio
import subprocess

import pytest
from agora_api.db import session_factory
from agora_api.events import Event
from agora_api.magna_constitution import (
    EPOCH_SECONDS,
    current_charter,
    current_constitution,
    settlement_decision,
)
from agora_api.models import ResearchReleaseSimulation
from sqlalchemy import select

from tests.conftest import register_agent

pytestmark = pytest.mark.security


async def _auth_agent(api_client, keypair, name):
    reg = await register_agent(api_client, keypair, name)
    return reg, {"Authorization": f"Bearer {reg['session_token']}"}


async def _bootstrap(api_client) -> None:
    response = await api_client.post("/v1/world/magna/bootstrap")
    assert response.status_code == 200, response.text


async def test_lower_level_charters_cannot_override_root_invariants(
    api_client, keypair, unique_name
):
    await _bootstrap(api_client)
    _, auth = await _auth_agent(api_client, keypair, unique_name)
    constitution = (await api_client.get("/v1/world/constitution")).json()
    science = (await api_client.get("/v1/worlds/science/charter")).json()

    async def evaluate(action: str, world_id: str = "science", caps: list[str] | None = None):
        return await api_client.post(
            "/v1/world/rules/evaluate",
            json={
                "world_instance_id": constitution["world_instance_id"],
                "current_constitution_hash": constitution["content_hash"],
                "current_charter_hash": science["content_hash"],
                "world_id": world_id,
                "requested_action": action,
                "resource_context": {"requested_capabilities": caps or []},
                "challenge_or_commitment_context": None,
                "as_of": "2026-08-29T00:00:00Z",
            },
            headers=auth,
        )

    truth = await evaluate("claim.truth_by_vote")
    assert truth.status_code == 200
    assert truth.json()["decision"] == "deny"
    assert "truth_not_vote" in truth.json()["reason_codes"]

    economy = (await api_client.get("/v1/worlds/economy/charter")).json()
    mint = await api_client.post(
        "/v1/world/rules/evaluate",
        json={
            "world_instance_id": constitution["world_instance_id"],
            "current_constitution_hash": constitution["content_hash"],
            "current_charter_hash": economy["content_hash"],
            "world_id": "economy",
            "requested_action": "tokoin.max_supply.modify",
            "resource_context": {},
            "challenge_or_commitment_context": None,
            "as_of": "2026-08-29T00:00:00Z",
        },
        headers=auth,
    )
    assert mint.json()["decision"] == "deny"
    assert "tokoin_fixed_supply" in mint.json()["reason_codes"]

    local_permission = await evaluate("world.observe", caps=["shell.execute", "secrets.read"])
    assert local_permission.json()["decision"] == "deny"
    assert "remote_rule_cannot_grant_local_permissions" in local_permission.json()["reason_codes"]


async def test_conflicting_charter_proposals_are_rejected(api_client, keypair, unique_name):
    await _bootstrap(api_client)
    _, auth = await _auth_agent(api_client, keypair, unique_name)
    async with session_factory()() as session:
        constitution = await current_constitution(session)
        charter = await current_charter(session, "science")
        payload = dict(charter.body)
        payload["permitted_actions"] = list(payload["permitted_actions"]) + ["claim.truth_by_vote"]
        payload["content_hash"] = charter.content_hash
        payload["signatures"] = charter.signatures
        await session.commit()
    response = await api_client.post(
        "/v1/worlds/science/charter-proposals",
        json={"idempotency_key": "bad-truth-vote", "proposed_charter": payload},
        headers=auth,
    )
    assert response.status_code == 422
    assert "truth_not_vote" in response.text
    assert constitution.content_hash


async def test_identical_rule_evaluation_is_deterministic(api_client, keypair, unique_name):
    await _bootstrap(api_client)
    _, auth = await _auth_agent(api_client, keypair, unique_name)
    constitution = (await api_client.get("/v1/world/constitution")).json()
    charter = (await api_client.get("/v1/worlds/forge/charter")).json()
    payload = {
        "world_instance_id": constitution["world_instance_id"],
        "current_constitution_hash": constitution["content_hash"],
        "current_charter_hash": charter["content_hash"],
        "world_id": "forge",
        "requested_action": "artifact.publish",
        "resource_context": {"requested_capabilities": []},
        "challenge_or_commitment_context": None,
        "as_of": "2026-08-29T00:00:00Z",
    }
    first = await api_client.post("/v1/world/rules/evaluate", json=payload, headers=auth)
    second = await api_client.post("/v1/world/rules/evaluate", json=payload, headers=auth)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["decision"] == "allow"

    async with session_factory()() as session:
        events = (
            (
                await session.execute(
                    select(Event).where(Event.event_type == "rule.evaluation.completed")
                )
            )
            .scalars()
            .all()
        )
    matching = [
        event
        for event in events
        if event.payload["receipt_id"] == first.json()["decision_receipt_id"]
    ]
    assert len(matching) == 1


async def test_research_release_policy_simulation_is_bounded_and_idempotent(
    api_client, keypair, unique_name
):
    _, auth = await _auth_agent(api_client, keypair, unique_name)
    policy = (await api_client.get("/v1/research/release-policy")).json()
    assert policy["policy"]["epoch_seconds"] == EPOCH_SECONDS
    assert policy["policy"]["release_limit"] == 1
    assert policy["policy"]["scheduler_implemented"] is True
    assert policy["policy"]["payment_before_resolution"] is False

    payload = {
        "idempotency_key": "epoch-one",
        "as_of": "2026-08-29T04:15:00Z",
        "last_successful_epoch_id": None,
        "candidates": [
            {
                "candidate_id": "weak",
                "state": "ELIGIBLE",
                "rank": 0,
                "eligibility_passed": False,
                "safety_passed": True,
                "rights_passed": True,
                "duplicate_check_passed": True,
                "test_escrow_reservation_receipt_id": "TEST-ESCROW-WEAK0001",
            },
            {
                "candidate_id": "strong",
                "state": "ELIGIBLE",
                "rank": 10,
                "eligibility_passed": True,
                "safety_passed": True,
                "rights_passed": True,
                "duplicate_check_passed": True,
                "test_escrow_reservation_receipt_id": "TEST-ESCROW-STRONG0001",
            },
            {
                "candidate_id": "second",
                "state": "ELIGIBLE",
                "rank": 11,
                "eligibility_passed": True,
                "safety_passed": True,
                "rights_passed": True,
                "duplicate_check_passed": True,
                "test_escrow_reservation_receipt_id": "TEST-ESCROW-SECOND0001",
            },
        ],
    }
    first, second = await asyncio.gather(
        api_client.post("/v1/research/release-policy/simulate", json=payload, headers=auth),
        api_client.post("/v1/research/release-policy/simulate", json=payload, headers=auth),
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert first.json()["released_count"] == 1
    assert first.json()["selected_candidate_id"] == "strong"
    assert first.json()["payment_authorized"] is False

    async with session_factory()() as session:
        rows = (
            (
                await session.execute(
                    select(ResearchReleaseSimulation).where(
                        ResearchReleaseSimulation.epoch_id == first.json()["epoch_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1


async def test_empty_epoch_and_downtime_do_not_create_catch_up_burst(
    api_client, keypair, unique_name
):
    _, auth = await _auth_agent(api_client, keypair, unique_name)
    response = await api_client.post(
        "/v1/research/release-policy/simulate",
        json={
            "idempotency_key": "empty-epoch",
            "as_of": "2026-08-29T08:00:00Z",
            "last_successful_epoch_id": (
                "agora-local-real:research-release-policy.v1:2026-08-28T00:00:00+00:00"
            ),
            "candidates": [],
        },
        headers=auth,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "NO_ELIGIBLE_CANDIDATE"
    assert body["released_count"] == 0
    assert body["downtime_recovery"] == "no_catch_up_burst"
    assert body["event_equivalent"] == "research.no_eligible_candidate"


def test_reward_payment_requires_resolved_verified_state():
    assert (
        settlement_decision("RELEASED_ACTIVE", valid_resolution=False)["payment_authorized"]
        is False
    )
    assert settlement_decision("UNDER_REVIEW", valid_resolution=True)["payment_authorized"] is False
    assert (
        settlement_decision("CLOSED_NONVIABLE", valid_resolution=False)["reservation_returned"]
        is True
    )
    assert (
        settlement_decision("RESOLVED_VERIFIED", valid_resolution=True)["payment_authorized"]
        is True
    )


def test_repo_contains_no_active_six_hour_release_policy():
    pattern = (
        r"(release|funding|candidate|reward|escrow).*"
        r"(21600|6h|six-hour|six hours|every-six-hours|cada 6 horas)|"
        r"(21600|6h|six-hour|six hours|every-six-hours|cada 6 horas).*"
        r"(release|funding|candidate|reward|escrow)"
    )
    result = subprocess.run(
        [
            "rg",
            "-n",
            pattern,
            "apps",
            "bridge",
            "packages",
            "docs",
            "tests",
        ],
        cwd="/home/merari-acero/agora",
        text=True,
        capture_output=True,
        check=False,
    )
    active_hits = [
        line
        for line in result.stdout.splitlines()
        if "tests/security/test_magna_rule_engine.py" not in line
        and "AGORA_MAGNA_ARQUITECTURA_2026" not in line
        and "superseded" not in line.lower()
        and "no remaining 6-hour" not in line.lower()
    ]
    assert active_hits == []
