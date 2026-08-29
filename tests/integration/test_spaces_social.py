"""Spaces, presence and social messages (S2-T06/07/10)."""

import secrets

import pytest
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.ids import new_mission_id
from agora_api.models import Event, Mission, Space
from agora_api.presence import list_present, mark_present, refresh_presence
from agora_api.ratelimit import get_redis
from sqlalchemy import func, select

from tests.conftest import register_agent

pytestmark = pytest.mark.integration

PLAZA = "spc_00000000000000000000P1AZA0"


async def test_central_plaza_seeded(api_client):
    r = await api_client.get("/v1/spaces")
    slugs = [s["slug"] for s in r.json()["spaces"]]
    assert "central-plaza" in slugs
    detail = await api_client.get(f"/v1/spaces/{PLAZA}")
    assert detail.json()["name"] == "Central Plaza"


async def test_enter_creates_presence_and_ledger_event(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    r = await api_client.post(
        f"/v1/spaces/{PLAZA}/enter",
        json={"movement_reason": "explicit_agent_decision"},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert r.status_code == 200
    present = await list_present(PLAZA)
    assert reg["agent_id"] in [a["agent_id"] for a in present]
    ttl = await get_redis().ttl(f"presence:{PLAZA}:{reg['agent_id']}")
    assert 0 < ttl <= 30  # TTL-based offline resolution
    async with session_factory()() as session:
        event = (
            await session.execute(
                select(Event)
                .where(Event.event_type == "space.entered")
                .order_by(Event.occurred_at.desc())
                .limit(1)
            )
        ).scalar_one()
    assert event.payload["movement_reason"] == "explicit_agent_decision"


async def test_heartbeats_never_touch_the_ledger(api_client, keypair, unique_name):
    """SEC-010: refreshing presence N times adds zero ledger rows."""
    reg = await register_agent(api_client, keypair, unique_name)
    await mark_present(PLAZA, reg["agent_id"], unique_name)
    async with session_factory()() as session:
        before = (await session.execute(select(func.count()).select_from(Event))).scalar_one()
    for _ in range(25):
        await refresh_presence(reg["agent_id"])
    async with session_factory()() as session:
        after = (await session.execute(select(func.count()).select_from(Event))).scalar_one()
    assert after == before


async def test_message_post_validate_and_list(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    content = f"Hello plaza {secrets.token_hex(4)}"
    r = await api_client.post(
        f"/v1/spaces/{PLAZA}/messages", json={"content": content}, headers=auth
    )
    assert r.status_code == 201
    message_id = r.json()["message_id"]
    assert message_id.startswith("msg_") and r.json()["event_id"].startswith("evt_")

    listing = await api_client.get(f"/v1/spaces/{PLAZA}/messages")
    found = [m for m in listing.json()["messages"] if m["message_id"] == message_id]
    assert found and found[0]["content"] == content and found[0]["agent_id"] == reg["agent_id"]

    second = await api_client.post(
        f"/v1/spaces/{PLAZA}/messages",
        json={"content": f"Second plaza {secrets.token_hex(4)}"},
        headers=auth,
    )
    assert second.status_code == 201
    cursor_listing = await api_client.get(
        f"/v1/spaces/{PLAZA}/messages",
        params={"after_message_id": message_id},
    )
    cursor_ids = [m["message_id"] for m in cursor_listing.json()["messages"]]
    assert second.json()["message_id"] in cursor_ids
    assert message_id not in cursor_ids

    # size + structure validation
    too_big = await api_client.post(
        f"/v1/spaces/{PLAZA}/messages", json={"content": "x" * 4001}, headers=auth
    )
    assert too_big.status_code == 422
    unknown = await api_client.post(
        f"/v1/spaces/{PLAZA}/messages",
        json={"content": "hi", "grant_permission": "shell.execute"},
        headers=auth,
    )
    assert unknown.status_code == 422
    unauth = await api_client.post(f"/v1/spaces/{PLAZA}/messages", json={"content": "x"})
    assert unauth.status_code == 401


async def test_revoked_device_cannot_enter_or_post(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    revoke = await api_client.post(f"/v1/devices/{reg['device_id']}/revoke", headers=auth)
    assert revoke.status_code == 200
    assert (
        await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    ).status_code == 403
    assert (
        await api_client.post(
            f"/v1/spaces/{PLAZA}/messages", json={"content": "x"}, headers=auth
        )
    ).status_code == 403


async def test_archived_challenge_space_is_read_only_for_enter_and_messages(
    api_client, keypair, unique_name
):
    reg = await register_agent(api_client, keypair, unique_name)
    archived_space_id = "spc_000000000000000000ARCHIV01"
    async with session_factory()() as session:
        ts = now_utc()
        session.add(
            Space(
                space_id=archived_space_id,
                slug=f"archived-challenge-{secrets.token_hex(3)}",
                name="Archived Challenge",
                kind="mission_challenge",
                description="Historical challenge space.",
                evidence_policy="optional",
                created_at=ts,
            )
        )
        session.add(
            Mission(
                mission_id=new_mission_id(),
                title="Archived challenge mission",
                objective="Remain historical and read-only.",
                description=None,
                state="archived",
                visibility="public",
                hosting_space_id=archived_space_id,
                challenge_kind="math_unsolved",
                max_participants=8,
                completion_policy={},
                created_by_agent_id=reg["agent_id"],
                created_by_agent_version_id=reg["agent_version_id"],
                created_at=ts,
            )
        )
        await session.commit()

    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    enter = await api_client.post(f"/v1/spaces/{archived_space_id}/enter", headers=auth)
    assert enter.status_code == 409
    assert enter.json()["error"]["code"] == "space_archived"

    post = await api_client.post(
        f"/v1/spaces/{archived_space_id}/messages",
        json={"content": "should not write to archived challenge"},
        headers=auth,
    )
    assert post.status_code == 409
    listing = await api_client.get(f"/v1/spaces/{archived_space_id}/messages")
    assert listing.status_code == 200
