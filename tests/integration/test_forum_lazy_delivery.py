"""Delivery work scales with actual readers; cursors cannot skip other forums."""

import pytest
from agora_api.db import session_factory
from agora_api.forum_consensus_service import (
    _get_or_create_forum,
    _get_or_create_thread,
    deliver_for_agent,
    publish_forum_post,
)
from agora_api.models import ForumDeliveryReceipt
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


async def test_lazy_receipts_and_per_forum_cursor(api_client, unique_name):
    agent = await register_agent(api_client, SigningKeypair(), unique_name)
    async with session_factory()() as session:
        forums = []
        posts = []
        for suffix in ("a", "b"):
            forum = await _get_or_create_forum(
                session,
                forum_type="WORLD_FORUM",
                scope_id=f"{unique_name}-{suffix}",
                visibility="PUBLIC",
                title=suffix,
                description="TEST",
            )
            forums.append(forum)
            thread = await _get_or_create_thread(session, forum=forum, title="TEST", metadata={})
            for index in range(3 if suffix == "a" else 1):
                posts.append(
                    await publish_forum_post(
                        session,
                        forum=forum,
                        thread=thread,
                        content=f"TEST-{index}",
                    )
                )
        await session.commit()
        event_ids = [post.event_id for post in posts]
        count = await session.scalar(
            select(func.count())
            .select_from(ForumDeliveryReceipt)
            .where(ForumDeliveryReceipt.event_id.in_(event_ids))
        )
        assert count == 0  # publication creates no per-agent rows
        cursor = {}
        seen = []
        # Drain, don't count: a fixed page budget made this test depend on how
        # many plaza posts earlier tests happened to leave in the world, so it
        # passed alone and failed in the full suite.
        for _ in range(500):
            page = await deliver_for_agent(
                session, agent_id=agent["agent_id"], cursor=cursor, limit=1
            )
            cursor = page["next_cursor"]
            seen.extend(post["event_id"] for post in page["posts"])
            if not page["posts"]:
                break
        else:
            raise AssertionError("delivery never drained — the cursor is not advancing")
        assert set(event_ids).issubset(seen)
        assert len(seen) == len(set(seen))
        assert cursor[forums[0].forum_id] == 3
        assert cursor[forums[1].forum_id] == 1
        replay = await deliver_for_agent(session, agent_id=agent["agent_id"], cursor={})
        assert set(event_ids).issubset(post["event_id"] for post in replay["posts"])
        count = await session.scalar(
            select(func.count())
            .select_from(ForumDeliveryReceipt)
            .where(ForumDeliveryReceipt.event_id.in_(event_ids))
        )
        assert count == 4  # replay updates receipts, never inserts duplicates
        await session.commit()


async def test_targeted_and_private_posts_do_not_leak(api_client, unique_name):
    agent = await register_agent(api_client, SigningKeypair(), unique_name)
    other = await register_agent(api_client, SigningKeypair(), unique_name + "-other")
    async with session_factory()() as session:
        event_ids = []
        for visibility in ("PUBLIC", "MEMBERS_ONLY"):
            forum = await _get_or_create_forum(
                session,
                forum_type="WORLD_FORUM",
                scope_id=unique_name + visibility,
                visibility=visibility,
                title="TEST",
                description="TEST",
            )
            thread = await _get_or_create_thread(session, forum=forum, title="TEST", metadata={})
            post = await publish_forum_post(
                session,
                forum=forum,
                thread=thread,
                content="TEST directed",
                metadata={"delivery_agent_ids": [other["agent_id"]]},
            )
            event_ids.append(post.event_id)
        await session.commit()
        feed = await deliver_for_agent(session, agent_id=agent["agent_id"], cursor={})
        assert not set(event_ids).intersection(post["event_id"] for post in feed["posts"])
        other_feed = await deliver_for_agent(session, agent_id=other["agent_id"], cursor={})
        received = {post["event_id"] for post in other_feed["posts"]}
        assert event_ids[0] in received
        assert event_ids[1] not in received
        await session.commit()
