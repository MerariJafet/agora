"""World topology, population and semantic movement (S3-T02/03/04/06/07)."""

import pytest
from agora_api.avatars import default_avatar
from agora_api.db import session_factory
from agora_api.models import Event
from agora_api.world import build_manifest, manifest_etag
from sqlalchemy import func, select

from tests.conftest import register_agent

pytestmark = pytest.mark.integration

PLAZA = "spc_00000000000000000000P1AZA0"
GARDEN = "spc_00000000000000000000GARDEN"


async def test_manifest_is_versioned_and_cacheable(api_client):
    first = await api_client.get("/v1/world/manifest")
    assert first.status_code == 200
    etag = first.headers["etag"]
    manifest = first.json()
    assert manifest["world_version"]
    assert manifest_etag(build_manifest()) == etag

    revalidated = await api_client.get(
        "/v1/world/manifest", headers={"If-None-Match": etag}
    )
    assert revalidated.status_code == 304  # topology is not re-downloaded


async def test_manifest_contains_no_presence(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    await api_client.post(
        f"/v1/spaces/{PLAZA}/enter",
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    manifest = (await api_client.get("/v1/world/manifest")).json()
    import json

    assert reg["agent_id"] not in json.dumps(manifest)
    # topology and presence are separate endpoints by design
    population = (await api_client.get("/v1/world/population")).json()
    assert reg["agent_id"] in json.dumps(population)


async def test_genesis_world_landmarks_seeded(api_client):
    manifest = (await api_client.get("/v1/world/manifest")).json()
    by_id = {lm["id"]: lm for lm in manifest["landmarks"]}
    assert by_id["central"]["state"] == "ACTIVE"
    for active in ("science", "economy", "ideas", "forge", "unknown"):
        assert by_id[active]["state"] == "ACTIVE"
        assert by_id[active]["space_id"]
    assert by_id["arena"]["state"] == "ACTIVE"
    assert by_id["arena"]["space_id"]
    assert by_id["world-pulse"]["state"] == "ACTIVE"
    assert by_id["world-pulse"]["space_id"]
    for future in ("observatory",):
        assert by_id[future]["state"] == "COMING_SOON"
        assert by_id[future]["space_id"] is None
    assert by_id["frontier"]["state"] == "ACTIVE"
    assert by_id["frontier"]["space_id"]

    spaces = (await api_client.get("/v1/spaces")).json()["spaces"]
    slugs = {s["slug"] for s in spaces}
    assert {
        "central-plaza",
        "science-district",
        "economy-district",
        "idea-garden",
        "the-forge",
        "the-unknown",
        "agora-arena",
        "world-pulse",
        "community-frontier",
    } <= slugs


async def test_population_reports_semantic_state(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    await api_client.post("/v1/agents/me/activity", json={"activity": "researching"},
                          headers=auth)

    population = (await api_client.get("/v1/world/population")).json()
    entry = next(
        a for a in population["spaces"][PLAZA]["agents"] if a["agent_id"] == reg["agent_id"]
    )
    assert entry["activity"] == "researching"
    assert entry["avatar"] == default_avatar(reg["agent_id"])
    assert population["spaces"][PLAZA]["count"] >= 1


async def test_space_transition_emits_origin_and_destination(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    moved = await api_client.post(f"/v1/spaces/{GARDEN}/enter", headers=auth)
    assert moved.status_code == 200 and moved.json()["transition"] is True

    async with session_factory()() as session:
        events = (
            await session.execute(
                select(Event).where(
                    Event.actor["agent_id"].astext == reg["agent_id"],
                    Event.event_type == "space.entered",
                )
            )
        ).scalars().all()
    transitions = [e.payload for e in events if e.payload["space_id"] == GARDEN]
    assert transitions and transitions[0]["from_space_id"] == PLAZA

    # the agent is present in exactly one space (old presence released)
    population = (await api_client.get("/v1/world/population")).json()
    present_in = [
        space_id for space_id, data in population["spaces"].items()
        if any(a["agent_id"] == reg["agent_id"] for a in data["agents"])
    ]
    assert present_in == [GARDEN]


async def test_reentering_same_space_is_semantically_idempotent(
    api_client, keypair, unique_name
):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    async with session_factory()() as session:
        before = (
            await session.execute(
                select(func.count()).where(
                    Event.actor["agent_id"].astext == reg["agent_id"],
                    Event.event_type == "space.entered",
                )
            )
        ).scalar_one()
    again = await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    assert again.json()["transition"] is False
    async with session_factory()() as session:
        after = (
            await session.execute(
                select(func.count()).where(
                    Event.actor["agent_id"].astext == reg["agent_id"],
                    Event.event_type == "space.entered",
                )
            )
        ).scalar_one()
    assert after == before  # no duplicate transition event


async def test_avatar_and_activity_updates_are_idempotent(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    spec = default_avatar(reg["agent_id"]) | {"body": "bot", "emblem": "atom"}
    first = await api_client.post("/v1/agents/me/avatar", json={"avatar": spec}, headers=auth)
    second = await api_client.post("/v1/agents/me/avatar", json={"avatar": spec}, headers=auth)
    assert first.json()["changed"] is True
    assert second.json()["changed"] is False  # no event for a no-op change

    a1 = await api_client.post("/v1/agents/me/activity", json={"activity": "writing"},
                               headers=auth)
    a2 = await api_client.post("/v1/agents/me/activity", json={"activity": "writing"},
                               headers=auth)
    assert a1.json()["changed"] is True and a2.json()["changed"] is False


async def test_world_events_are_semantic_only(api_client, keypair, unique_name):
    """No coordinate, frame or pixel data may reach the ledger."""
    import json

    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    await api_client.post("/v1/agents/me/activity", json={"activity": "building"},
                          headers=auth)
    events = (
        await api_client.get(f"/v1/agents/{reg['agent_id']}/events")
    ).json()["events"]
    serialized = json.dumps(events)
    for forbidden in ('"x"', '"y"', "frame", "sprite", "tween", "camera"):
        assert forbidden not in serialized
