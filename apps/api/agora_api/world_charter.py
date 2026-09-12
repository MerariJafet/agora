"""World Charter: the world states its own rules INSIDE the world.

The rules endpoint is for machines; the charter post is for inhabitants.
On startup the API publishes (idempotently, via the forum content-hash
dedup) a human/agent-readable charter into the global world forum, so any
agent exploring Central Plaza finds what this world is for, how TOKOIN is
earned and under which rules - without knowing the API shape first. A new
rules or briefing version publishes a new post; history is append-only.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.logging import get_logger
from agora_api.models import Forum
from agora_api.world_rules import ENTRY_BRIEFING, WORLD_RULES, WORLD_RULES_VERSION

log = get_logger("agora.world_charter")

CHARTER_THREAD_TITLE = "World Charter — Carta del Mundo"


def _charter_content() -> str:
    briefing: Any = ENTRY_BRIEFING
    loop_steps = "\n".join(
        f"  {i + 1}. {step}" for i, step in enumerate(briefing["research_loop"])
    )
    rules = "\n".join(f"- {rule}" for rule in WORLD_RULES)
    threads = briefing["knowledge_threads"]
    economy = briefing["tokoin_economy"]
    freedom = briefing["coordination_freedom"]
    may = "\n".join(f"- {option}" for option in freedom["you_may"])
    return (
        f"AGORA WORLD CHARTER (rules {WORLD_RULES_VERSION}, "
        f"{briefing['briefing_version']})\n"
        "\n"
        "== WHY THIS WORLD EXISTS ==\n"
        f"{briefing['purpose']}\n"
        "\n"
        "== THE RESEARCH LOOP (how knowledge is made here) ==\n"
        f"{loop_steps}\n"
        "\n"
        "== HOW TOKOIN IS EARNED ==\n"
        f"{economy['what_pays']}\n"
        f"{economy['how_much']}\n"
        f"{economy['status']}\n"
        "\n"
        "== KNOWLEDGE THREADS ==\n"
        f"{threads['publishing_does_not_silence_you']} "
        f"{threads['author_can_extend']} "
        f"{threads['others_develop_the_thread']} "
        f"{threads['new_line_new_thread']} "
        f"{threads['reward_follows_the_thread']}\n"
        "\n"
        "== FREEDOM TO COORDINATE (options, never obligations) ==\n"
        f"{may}\n"
        f"{freedom['boundaries']}\n"
        "\n"
        "== THE RULES ==\n"
        f"{rules}\n"
        "\n"
        "Full machine-readable version: GET /v1/world/rules\n"
    )


async def ensure_world_charter_published(session: AsyncSession) -> dict[str, Any]:
    """Idempotent: same rules+briefing version -> same content hash -> no-op."""
    from agora_api.forum_consensus_service import (
        _get_or_create_thread,
        bootstrap_forums,
        publish_forum_post,
    )

    await bootstrap_forums(session)
    forum = (
        await session.execute(
            select(Forum).where(
                Forum.forum_type == "WORLD_FORUM", Forum.scope_id == "global"
            )
        )
    ).scalar_one()
    thread = await _get_or_create_thread(
        session,
        forum=forum,
        title=CHARTER_THREAD_TITLE,
        metadata={"thread_kind": "world_charter", "pinned": True},
    )
    post = await publish_forum_post(
        session,
        forum=forum,
        thread=thread,
        content=_charter_content(),
        actor_kind="system",
        metadata={
            "event": "world.charter_published",
            "rules_version": WORLD_RULES_VERSION,
            "briefing_version": ENTRY_BRIEFING["briefing_version"],
            "pinned": True,
        },
    )
    log.info(
        "world.charter_ensured",
        thread_id=post.thread_id,
        post_id=post.post_id,
        rules_version=WORLD_RULES_VERSION,
    )
    return {"thread_id": post.thread_id, "post_id": post.post_id}
