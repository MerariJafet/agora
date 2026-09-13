"""Mentions network (ADR-0072): @mention/@group/@todos fanout + inbox.

Coexistence-robust: nothing here assumes a virgin database. Agents, spaces
and group slugs are unique per test, and assertions target THIS test's
sources (source_id) instead of global counts.

The `api_client` fixture is shadowed locally to include the mentions router:
main.py is owned by the founder and gets the one-line registration later.
"""

import httpx
import pytest
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.ids import new_space_id
from agora_api.mentions_service import parse_mentions
from agora_api.models import Space
from agora_api.provenance import add_provenance

from tests.conftest import SigningKeypair, register_agent
from tests.integration.test_challenge_knowledge_threads import _contribute
from tests.integration.test_mission_challenges import (
    _auth,
    _cancel_test_challenge,
    _join,
    _seed_challenge,
    _submit,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def api_client():
    """Same in-process client as tests/conftest.py, plus the mentions router
    (registered here because main.py is intentionally not touched by this
    change; the founder adds the include_router line)."""
    from agora_api.config import get_settings
    from agora_api.main import create_app
    from agora_api.routes import mentions
    from agora_api.test_isolation import assert_safe_test_environment

    get_settings.cache_clear()
    assert_safe_test_environment()
    app = create_app()
    app.include_router(mentions.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed_plaza(unique_name: str) -> str:
    space_id = new_space_id()
    async with session_factory()() as session:
        session.add(
            Space(
                space_id=space_id,
                slug=f"mentions-{unique_name.lower()}",
                name=f"Mentions plaza {unique_name}",
                kind="plaza",
                description="Ephemeral test plaza for the mentions network.",
                evidence_policy="optional",
                created_at=now_utc(),
            )
        )
        await add_provenance(
            session,
            record_table="spaces",
            record_id=space_id,
            created_by="test.seed_mentions",
            source_reference=unique_name,
        )
        await session.commit()
    return space_id


async def _post(api_client, space_id: str, reg: dict, content: str) -> dict:
    response = await api_client.post(
        f"/v1/spaces/{space_id}/messages", json={"content": content}, headers=_auth(reg)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _inbox(api_client, reg: dict, **params) -> dict:
    response = await api_client.get(
        "/v1/agents/me/notifications", params=params, headers=_auth(reg)
    )
    assert response.status_code == 200, response.text
    return response.json()


def _for_source(inbox: dict, source_id: str) -> list[dict]:
    return [n for n in inbox["notifications"] if n["source_id"] == source_id]


async def _create_group(api_client, reg: dict, slug: str, name: str) -> httpx.Response:
    return await api_client.post(
        "/v1/groups",
        json={"slug": slug, "name": name, "description": "Working group for tests."},
        headers=_auth(reg),
    )


def test_parse_mentions_is_deterministic():
    parsed = parse_mentions(
        "hola @Nobel-Maximo y @todos: revisen @core-team, no a@b ni email@example",
        known_group_slugs={"core-team"},
    )
    assert parsed["broadcast"] is True
    assert "nobel-maximo" in parsed["agent_names"]
    assert parsed["group_slugs"] == {"core-team"}
    # 'example' after 'email@' is not a mention; bare '@b' preceded by a word
    # character is not a mention either.
    assert "example" not in parsed["agent_names"]
    assert "b" not in parsed["agent_names"]


async def test_direct_mention_in_social_message(api_client, unique_name):
    author = await register_agent(api_client, SigningKeypair(), f"{unique_name}-author")
    target = await register_agent(api_client, SigningKeypair(), f"{unique_name}-target")
    space_id = await _seed_plaza(unique_name)

    content = f"@{unique_name}-target can you review the sprint board?"
    message = await _post(api_client, space_id, author, content)

    inbox = await _inbox(api_client, target)
    notifications = _for_source(inbox, message["message_id"])
    assert len(notifications) == 1, inbox
    notification = notifications[0]
    assert notification["kind"] == "mention"
    assert notification["source_type"] == "social_message"
    assert notification["snippet"] == content
    assert notification["context"] == {"space_id": space_id}
    assert notification["created_by_agent_id"] == author["agent_id"]
    assert notification["read_at"] is None
    assert inbox["total_unread"] >= 1

    # The author never notifies themselves, even mentioning their own name.
    self_message = await _post(
        api_client, space_id, author, f"@{unique_name}-author note to self"
    )
    author_inbox = await _inbox(api_client, author)
    assert _for_source(author_inbox, message["message_id"]) == []
    assert _for_source(author_inbox, self_message["message_id"]) == []


async def test_group_mention_reaches_members_except_author(api_client, unique_name):
    suffix = unique_name.split("-", 1)[1].lower()
    slug = f"team-{suffix}"
    owner = await register_agent(api_client, SigningKeypair(), f"{unique_name}-owner")
    member_b = await register_agent(api_client, SigningKeypair(), f"{unique_name}-bee")
    member_c = await register_agent(api_client, SigningKeypair(), f"{unique_name}-cee")
    outsider = await register_agent(api_client, SigningKeypair(), f"{unique_name}-out")
    space_id = await _seed_plaza(unique_name)

    created = await _create_group(api_client, owner, slug, f"Team {suffix}")
    assert created.status_code == 201, created.text
    assert created.json()["member_count"] == 1

    for reg in (member_b, member_c):
        joined = await api_client.post(f"/v1/groups/{slug}/join", headers=_auth(reg))
        assert joined.status_code == 200, joined.text
    detail = await api_client.get(f"/v1/groups/{slug}")
    assert detail.status_code == 200
    assert detail.json()["member_count"] == 3
    roles = {m["agent_id"]: m["role"] for m in detail.json()["members"]}
    assert roles[owner["agent_id"]] == "owner"
    assert roles[member_b["agent_id"]] == "member"

    listing = await api_client.get("/v1/groups")
    listed = [g for g in listing.json()["groups"] if g["slug"] == slug]
    assert listed and listed[0]["member_count"] == 3

    message = await _post(api_client, space_id, member_b, f"@{slug} daily sync in the plaza")
    for reg in (owner, member_c):
        notifications = _for_source(await _inbox(api_client, reg), message["message_id"])
        assert len(notifications) == 1, reg["agent_id"]
        assert notifications[0]["kind"] == "group_mention"
    # The author and non-members get nothing.
    assert _for_source(await _inbox(api_client, member_b), message["message_id"]) == []
    assert _for_source(await _inbox(api_client, outsider), message["message_id"]) == []


async def test_duplicate_slug_rejected_and_leave_exits_fanout(api_client, unique_name):
    suffix = unique_name.split("-", 1)[1].lower()
    slug = f"crew-{suffix}"
    owner = await register_agent(api_client, SigningKeypair(), f"{unique_name}-owner")
    leaver = await register_agent(api_client, SigningKeypair(), f"{unique_name}-leaver")
    space_id = await _seed_plaza(unique_name)

    assert (await _create_group(api_client, owner, slug, "Crew")).status_code == 201
    duplicate = await _create_group(api_client, leaver, slug, "Crew clone")
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "conflict"

    joined = await api_client.post(f"/v1/groups/{slug}/join", headers=_auth(leaver))
    assert joined.status_code == 200 and joined.json()["member_count"] == 2

    before = await _post(api_client, space_id, owner, f"@{slug} kickoff before leave")
    assert len(_for_source(await _inbox(api_client, leaver), before["message_id"])) == 1

    left = await api_client.post(f"/v1/groups/{slug}/leave", headers=_auth(leaver))
    assert left.status_code == 200 and left.json()["member_count"] == 1
    again = await api_client.post(f"/v1/groups/{slug}/leave", headers=_auth(leaver))
    assert again.status_code == 409

    after = await _post(api_client, space_id, owner, f"@{slug} planning after leave")
    assert _for_source(await _inbox(api_client, leaver), after["message_id"]) == []


async def test_broadcast_reaches_world_and_is_throttled(api_client, unique_name):
    author = await register_agent(api_client, SigningKeypair(), f"{unique_name}-caster")
    listener_a = await register_agent(api_client, SigningKeypair(), f"{unique_name}-la")
    listener_b = await register_agent(api_client, SigningKeypair(), f"{unique_name}-lb")
    space_id = await _seed_plaza(unique_name)

    first = await _post(api_client, space_id, author, "@todos world checkpoint one")
    second = await _post(api_client, space_id, author, "@all world checkpoint two")
    third = await _post(api_client, space_id, author, "@todos world checkpoint three")

    for reg in (listener_a, listener_b):
        inbox = await _inbox(api_client, reg)
        first_hits = _for_source(inbox, first["message_id"])
        second_hits = _for_source(inbox, second["message_id"])
        assert len(first_hits) == 1 and first_hits[0]["kind"] == "broadcast"
        assert len(second_hits) == 1 and second_hits[0]["kind"] == "broadcast"
        # Third broadcast within the hour is silently dropped: zero new
        # notifications from that source for anyone.
        assert _for_source(inbox, third["message_id"]) == []
    author_inbox = await _inbox(api_client, author)
    for message in (first, second, third):
        assert _for_source(author_inbox, message["message_id"]) == []


async def test_mention_in_thread_contribution_carries_challenge_context(
    api_client, unique_name
):
    submitter, challenge = await _seed_challenge(api_client, unique_name)
    peer = await register_agent(api_client, SigningKeypair(), f"{unique_name}-peer")
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
                f"@{unique_name}-creator the bounded range needs a failure-mode "
                "table before this argument can be replicated."
            ),
        )
        assert contribution.status_code == 201, contribution.text
        contribution_id = contribution.json()["contribution"]["contribution_id"]

        inbox = await _inbox(api_client, submitter)
        notifications = _for_source(inbox, contribution_id)
        assert len(notifications) == 1, inbox
        notification = notifications[0]
        assert notification["kind"] == "mention"
        assert notification["source_type"] == "thread_contribution"
        assert notification["context"] == {
            "mission_id": mission_id,
            "submission_id": submission["submission_id"],
        }
        assert notification["created_by_agent_id"] == peer["agent_id"]
    finally:
        await _cancel_test_challenge(mission_id)


async def test_inbox_ordering_and_mark_read(api_client, unique_name):
    author = await register_agent(api_client, SigningKeypair(), f"{unique_name}-writer")
    reader = await register_agent(api_client, SigningKeypair(), f"{unique_name}-reader")
    space_id = await _seed_plaza(unique_name)

    target = f"@{unique_name}-reader"
    m1 = await _post(api_client, space_id, author, f"{target} first ping")
    m2 = await _post(api_client, space_id, author, f"{target} second ping")
    m3 = await _post(api_client, space_id, author, f"{target} third ping")

    inbox = await _inbox(api_client, reader)
    assert inbox["total_unread"] == 3
    sources = [n["source_id"] for n in inbox["notifications"]]
    assert sources[:3] == [m3["message_id"], m2["message_id"], m1["message_id"]]

    # Mark ONE read: it drops behind every unread entry.
    read_id = _for_source(inbox, m2["message_id"])[0]["notification_id"]
    marked = await api_client.post(
        "/v1/agents/me/notifications/read",
        json={"notification_ids": [read_id]},
        headers=_auth(reader),
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["marked_read"] == 1

    inbox = await _inbox(api_client, reader)
    assert inbox["total_unread"] == 2
    ordered = [n["source_id"] for n in inbox["notifications"]]
    assert ordered[:3] == [m3["message_id"], m1["message_id"], m2["message_id"]]
    assert inbox["notifications"][2]["read_at"] is not None

    unread_only = await _inbox(api_client, reader, unread_only="true")
    assert {n["source_id"] for n in unread_only["notifications"]} == {
        m1["message_id"],
        m3["message_id"],
    }

    # Mark ALL: idempotent on already-read rows.
    all_marked = await api_client.post(
        "/v1/agents/me/notifications/read", json={"all": True}, headers=_auth(reader)
    )
    assert all_marked.status_code == 200
    assert all_marked.json()["marked_read"] == 2
    final = await _inbox(api_client, reader)
    assert final["total_unread"] == 0
    assert all(n["read_at"] is not None for n in final["notifications"][:3])

    empty_body = await api_client.post(
        "/v1/agents/me/notifications/read", json={}, headers=_auth(reader)
    )
    assert empty_body.status_code == 422


async def test_same_source_never_duplicates_per_receiver(api_client, unique_name):
    suffix = unique_name.split("-", 1)[1].lower()
    slug = f"dedup-{suffix}"
    author = await register_agent(api_client, SigningKeypair(), f"{unique_name}-author")
    doubled = await register_agent(api_client, SigningKeypair(), f"{unique_name}-double")
    space_id = await _seed_plaza(unique_name)

    assert (await _create_group(api_client, author, slug, "Dedup crew")).status_code == 201
    joined = await api_client.post(f"/v1/groups/{slug}/join", headers=_auth(doubled))
    assert joined.status_code == 200

    # Direct mention + group mention + repeated token in ONE message:
    # exactly one notification, with the most specific kind.
    message = await _post(
        api_client,
        space_id,
        author,
        f"@{unique_name}-double @{slug} @{unique_name}-double please sync the notes",
    )
    inbox = await _inbox(api_client, doubled)
    notifications = _for_source(inbox, message["message_id"])
    assert len(notifications) == 1, inbox
    assert notifications[0]["kind"] == "mention"
