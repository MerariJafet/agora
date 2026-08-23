"""Spaces, presence and social messages (S2-T06/07/10)."""

import secrets

import pytest
from sqlalchemy import func, select

from agora_api.db import session_factory
from agora_api.models import Event
from agora_api.presence import list_present, mark_present, refresh_presence
from agora_api.ratelimit import get_redis
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
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert r.status_code == 200
    present = await list_present(PLAZA)
    assert reg["agent_id"] in [a["agent_id"] for a in present]
    ttl = await get_redis().ttl(f"presence:{PLAZA}:{reg['agent_id']}")
    assert 0 < ttl <= 30  # TTL-based offline resolution


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