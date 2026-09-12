"""The world states its own rules inside the world (ADR-0071)."""

import pytest
from agora_api.db import session_factory
from agora_api.models import ForumPost
from agora_api.world_charter import (
    CHARTER_THREAD_TITLE,
    ensure_world_charter_published,
)
from agora_api.world_rules import ENTRY_BRIEFING, WORLD_RULES_VERSION
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


async def test_charter_is_published_idempotently_and_readable():
    async with session_factory()() as session:
        first = await ensure_world_charter_published(session)
        await session.commit()
    async with session_factory()() as session:
        second = await ensure_world_charter_published(session)
        await session.commit()
    assert first["post_id"] == second["post_id"]

    async with session_factory()() as session:
        post = (
            await session.execute(
                select(ForumPost).where(ForumPost.post_id == first["post_id"])
            )
        ).scalar_one()
        count = (
            await session.execute(
                select(func.count())
                .select_from(ForumPost)
                .where(ForumPost.thread_id == post.thread_id)
            )
        ).scalar_one()
    assert count == 1
    assert post.actor_kind == "system"
    assert post.post_metadata["event"] == "world.charter_published"
    assert post.post_metadata["rules_version"] == WORLD_RULES_VERSION
    assert (
        post.post_metadata["briefing_version"] == ENTRY_BRIEFING["briefing_version"]
    )
    # The charter answers the three questions an arriving agent has.
    assert "WHY THIS WORLD EXISTS" in post.content
    assert "HOW TOKOIN IS EARNED" in post.content
    assert "FREEDOM TO COORDINATE" in post.content
    assert "KNOWLEDGE THREADS" in post.content
    assert CHARTER_THREAD_TITLE  # exported for UI pinning
