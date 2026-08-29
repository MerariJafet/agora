import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from agora_api.db import session_factory
from agora_api.events import Event
from agora_api.magna_constitution import (
    CHARTER_VERSION,
    charter_body,
    current_charter,
    current_constitution,
)
from agora_api.models import AgentCharterAcceptance, RuleDeliveryState, WorldCharter
from sqlalchemy import select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


async def test_constitution_and_ten_world_charters_are_seeded_and_cacheable(api_client):
    response = await api_client.get("/v1/world/constitution")
    assert response.status_code == 200, response.text
    assert response.headers["etag"]
    body = response.json()
    assert body["version"] == "magna-root-1.0.0"
    assert body["body"]["research_release_rule"]["epoch_seconds"] == 7200
    assert body["body"]["research_release_rule"]["release_limit"] == 1
    assert body["body"]["research_release_rule"]["scheduler_implemented"] is False

    revalidated = await api_client.get(
        "/v1/world/constitution", headers={"If-None-Match": response.headers["etag"]}
    )
    assert revalidated.status_code == 304

    expected = {
        "research-commons",
        "science",
        "economy",
        "civic",
        "forge",
        "replication-court",
        "arena",
        "community-frontier",
        "unknown",
        "commercialization",
    }
    async with session_factory()() as session:
        constitution = await current_constitution(session)
        rows = (
            (
                await session.execute(
                    select(WorldCharter).where(
                        WorldCharter.constitution_hash == constitution.content_hash,
                        WorldCharter.state == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert {row.world_id for row in rows} == expected


async def test_world_charter_acceptance_is_idempotent_under_retry_and_concurrency(
    api_client, keypair, unique_name
):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    charter = (await api_client.get("/v1/worlds/science/charter")).json()
    payload = {
        "idempotency_key": "accept-science-v1",
        "charter_hash": charter["content_hash"],
        "constitution_hash": charter["constitution_hash"],
    }

    responses = await asyncio.gather(
        *[
            api_client.post(
                f"/v1/worlds/science/charters/{CHARTER_VERSION}/accept",
                json=payload,
                headers=auth,
            )
            for _ in range(4)
        ]
    )
    assert {response.status_code for response in responses} == {200}
    acceptance_ids = {response.json()["acceptance_id"] for response in responses}
    assert len(acceptance_ids) == 1
    assert responses[0].json()["local_permissions_granted"] == []

    async with session_factory()() as session:
        acceptances = (
            (
                await session.execute(
                    select(AgentCharterAcceptance).where(
                        AgentCharterAcceptance.agent_id == reg["agent_id"],
                        AgentCharterAcceptance.world_id == "science",
                    )
                )
            )
            .scalars()
            .all()
        )
        events = (
            (
                await session.execute(
                    select(Event).where(Event.event_type == "world.charter.accepted")
                )
            )
            .scalars()
            .all()
        )
    assert len(acceptances) == 1
    matching_events = [
        event
        for event in events
        if event.payload.get("acceptance_id") == next(iter(acceptance_ids))
    ]
    assert len(matching_events) == 1


async def test_expired_downgraded_and_badly_signed_charters_are_rejected(
    api_client, keypair, unique_name
):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    charter = (await api_client.get("/v1/worlds/economy/charter")).json()
    payload = {
        "idempotency_key": "accept-economy-v1",
        "charter_hash": charter["content_hash"],
        "constitution_hash": charter["constitution_hash"],
    }

    downgraded = await api_client.post(
        "/v1/worlds/economy/charters/0.9.0/accept", json=payload, headers=auth
    )
    assert downgraded.status_code == 404

    async with session_factory()() as session:
        row = await current_charter(session, "economy")
        row.signatures = [{"issuer_key_id": "bad", "signature": {"domain": "wrong"}}]
        await session.commit()
    bad_signature = await api_client.post(
        f"/v1/worlds/economy/charters/{CHARTER_VERSION}/accept", json=payload, headers=auth
    )
    assert bad_signature.status_code == 401
    assert bad_signature.json()["error"]["code"] == "signature_invalid"

    async with session_factory()() as session:
        constitution = await current_constitution(session)
        row = await current_charter(session, "economy")
        restored = charter_body(
            "economy", constitution.content_hash, constitution.world_instance_id
        )
        row.signatures = restored["signatures"]
        civic = await current_charter(session, "civic")
        civic.sunset_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    civic_charter = (await api_client.get("/v1/worlds/civic/charter")).json()
    expired = await api_client.post(
        f"/v1/worlds/civic/charters/{CHARTER_VERSION}/accept",
        json={
            "idempotency_key": "accept-civic-expired",
            "charter_hash": civic_charter["content_hash"],
            "constitution_hash": civic_charter["constitution_hash"],
        },
        headers=auth,
    )
    assert expired.status_code == 401
    async with session_factory()() as session:
        civic = await current_charter(session, "civic")
        civic.sunset_at = None
        await session.commit()


async def test_charter_proposal_rejection_is_authorized_and_audited(
    api_client, keypair, unique_name
):
    first = await register_agent(api_client, keypair, unique_name)
    second = await register_agent(api_client, SigningKeypair(), unique_name + "-other")
    first_auth = {"Authorization": f"Bearer {first['session_token']}"}
    second_auth = {"Authorization": f"Bearer {second['session_token']}"}
    async with session_factory()() as session:
        charter = await current_charter(session, "unknown")
        payload = dict(charter.body)
        await session.commit()

    proposal_response = await api_client.post(
        "/v1/worlds/unknown/charter-proposals",
        json={"idempotency_key": "unknown-proposal", "proposed_charter": payload},
        headers=first_auth,
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_id = proposal_response.json()["proposal_id"]

    unauthorized = await api_client.post(
        f"/v1/worlds/unknown/charter-proposals/{proposal_id}/reject",
        json={"reason": "not mine"},
        headers=second_auth,
    )
    assert unauthorized.status_code == 403

    rejected = await api_client.post(
        f"/v1/worlds/unknown/charter-proposals/{proposal_id}/reject",
        json={"reason": "superseded by stronger draft"},
        headers=first_auth,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"

    retry = await api_client.post(
        f"/v1/worlds/unknown/charter-proposals/{proposal_id}/reject",
        json={"reason": "duplicate"},
        headers=first_auth,
    )
    assert retry.status_code == 200
    async with session_factory()() as session:
        events = (
            (
                await session.execute(
                    select(Event).where(Event.event_type == "world.charter.rejected")
                )
            )
            .scalars()
            .all()
        )
    matching = [event for event in events if event.payload.get("proposal_id") == proposal_id]
    assert len(matching) == 1


async def test_constitution_endpoints_do_not_reset_rule_feed_cursor(
    api_client, keypair, unique_name
):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    feed = await api_client.get("/v1/world/rules/feed", headers=auth)
    assert feed.status_code == 200
    rule = feed.json()["rules"][0]
    cursor = await api_client.post(
        "/v1/world/rules/cursor",
        json={"rule_id": rule["rule_id"], "sequence_number": rule["sequence_number"]},
        headers=auth,
    )
    assert cursor.status_code == 200

    before = await _cursor_rows(reg["agent_id"])
    assert (await api_client.get("/v1/world/constitution")).status_code == 200
    assert (await api_client.get("/v1/worlds/science/charter")).status_code == 200
    after = await _cursor_rows(reg["agent_id"])
    assert after == before


async def _cursor_rows(agent_id: str):
    async with session_factory()() as session:
        rows = (
            await session.execute(
                select(
                    RuleDeliveryState.rule_id,
                    RuleDeliveryState.agent_id,
                    RuleDeliveryState.cursor_sequence,
                    RuleDeliveryState.technical_state,
                ).where(RuleDeliveryState.agent_id == agent_id)
            )
        ).all()
    return [(str(a), str(b), int(c), str(d)) for a, b, c, d in rows]
