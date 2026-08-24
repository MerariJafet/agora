"""Mandatory Sprint 07 E2E: One Event, Many Minds."""

import asyncio

import pytest

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.e2e

PULSE_SPACE = "spc_00000000000000000000PULSE"


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _register(api_client, name: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), name)


async def test_one_event_many_minds(api_client, unique_name):
    agents = [
        await _register(api_client, f"{unique_name}-mind-{i:02d}")
        for i in range(20)
    ]
    coordinator = agents[0]
    query = f"solar storm public event {unique_name}"

    # 20 agents ask the same public-source question; coalescing/cache means one
    # upstream adapter call for this source/query.
    responses = await asyncio.gather(
        *[
            api_client.post(
                "/v1/knowledge/search",
                json={"source_id": "gdelt_world_pulse", "query": query},
                headers=_auth(agent),
            )
            for agent in agents
        ]
    )
    assert all(response.status_code == 201 for response in responses)
    snapshots = [response.json() for response in responses]
    assert len({snapshot["snapshot_id"] for snapshot in snapshots}) == 1
    snapshot = snapshots[0]
    assert snapshot["freshness_contract"] == "NEAR_REALTIME"
    assert snapshot["license_terms"]

    # A second allowed source clusters into the same World Pulse event without
    # rewriting the original snapshot.
    nasa_snapshot = (
        await api_client.post(
            "/v1/knowledge/search",
            json={"source_id": "nasa_public", "query": query, "force_refresh": True},
            headers=_auth(coordinator),
        )
    ).json()
    assert nasa_snapshot["snapshot_id"] != snapshot["snapshot_id"]

    pulse_events = (await api_client.get("/v1/world-pulse/events")).json()["events"]
    pulse = next(event for event in pulse_events if query.title() in event["title"])
    assert pulse["source_count"] >= 2
    assert pulse["latest_snapshot_id"] == nasa_snapshot["snapshot_id"]

    claim = (
        await api_client.post(
            "/v1/claims",
            json={
                "space_id": PULSE_SPACE,
                "claim_type": "observation",
                "text": "Multiple public sources report the same solar event cluster.",
                "language": "en",
            },
            headers=_auth(coordinator),
        )
    ).json()

    evidence = await api_client.post(
        f"/v1/knowledge/snapshots/{snapshot['snapshot_id']}/evidence",
        json={"claim_id": claim["claim_id"], "role": "supports"},
        headers=_auth(coordinator),
    )
    assert evidence.status_code == 201, evidence.text
    assert evidence.json()["provenance_level"] == "agora_verified_snapshot"
    assert evidence.json()["content_hash"] == snapshot["content_hash"]

    debate = (
        await api_client.post(
            f"/v1/spaces/{PULSE_SPACE}/debates",
            json={
                "question": "Should World Pulse freshness be treated as realtime truth?",
                "positions": ["YES", "NO"],
                "max_participants": 4,
                "evidence_policy": "optional",
            },
            headers=_auth(coordinator),
        )
    ).json()
    mission = (
        await api_client.post(
            "/v1/missions",
            json={
                "title": "Analyze a pinned World Pulse event",
                "objective": "Use the pinned KnowledgeSnapshot without chasing latest.",
                "hosting_space_id": PULSE_SPACE,
                "related_debate_id": debate["debate_id"],
                "related_claim_ids": [claim["claim_id"]],
                "completion_policy": {"minimum_independent_reviews": 0},
            },
            headers=_auth(coordinator),
        )
    ).json()
    assert mission["related_debate_id"] == debate["debate_id"]
    assert claim["claim_id"] in mission["related_claim_ids"]

    # A source change creates a new immutable snapshot, but the Claim Evidence
    # remains pinned to the original snapshot/content hash.
    changed = (
        await api_client.post(
            "/v1/knowledge/search",
            json={"source_id": "gdelt_world_pulse", "query": query, "force_refresh": True},
            headers=_auth(coordinator),
        )
    ).json()
    assert changed["snapshot_id"] != snapshot["snapshot_id"]
    evidence_rows = (
        await api_client.get(f"/v1/claims/{claim['claim_id']}/evidence")
    ).json()["evidence"]
    assert evidence_rows[0]["locator"] == f"knowledge://snapshot/{snapshot['snapshot_id']}"
    assert evidence_rows[0]["content_hash"] == snapshot["content_hash"]

    ssrf = await api_client.post(
        "/v1/knowledge/search",
        json={"source_id": "gdelt_world_pulse", "query": "http://169.254.169.254/latest"},
        headers=_auth(coordinator),
    )
    assert ssrf.status_code == 422

