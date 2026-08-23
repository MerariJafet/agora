"""Seed/clear synthetic world presence against the RUNNING dev stack.

Used to measure real browser FPS at 100/500/1000 inhabitants without running
that many Bridges or a single model call.

  .venv/bin/python scripts/seed_synthetic_presence.py seed 500
  .venv/bin/python scripts/seed_synthetic_presence.py clear
"""

import asyncio
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

SPACES = [
    "spc_00000000000000000000P1AZA0",
    "spc_0000000000000000000SCIENCE",
    "spc_0000000000000000000ECONOMY",
    "spc_00000000000000000000GARDEN",
    "spc_000000000000000000000FORGE",
    "spc_0000000000000000000UNKNOWN",
]
MARKER = "SynthLoad-"


async def seed(count: int) -> None:
    from agora_api.avatars import PALETTE, default_avatar
    from agora_api.db import session_factory
    from agora_api.events import now_utc
    from agora_api.ids import new_agent_id
    from agora_api.models import Agent
    from agora_api.presence import mark_present

    activities = ["idle", "reading", "discussing", "researching", "computing",
                  "building", "writing", "exploring"]
    created: list[tuple[str, str]] = []
    async with session_factory()() as session:
        for i in range(count):
            agent_id = new_agent_id()
            avatar = default_avatar(agent_id)
            avatar["tint"] = PALETTE[i % len(PALETTE)]
            session.add(Agent(
                agent_id=agent_id, name=f"{MARKER}{i}", status="registered",
                avatar=avatar, activity=activities[i % len(activities)],
                created_at=now_utc(), updated_at=now_utc(),
            ))
            created.append((agent_id, SPACES[i % len(SPACES)]))
        await session.commit()
    for agent_id, space_id in created:
        await mark_present(space_id, agent_id, f"{MARKER}{secrets.token_hex(2)}")
    print(f"seeded {count} synthetic agents across {len(SPACES)} spaces")


async def clear() -> None:
    from agora_api.db import session_factory
    from agora_api.models import Agent
    from agora_api.presence import mark_absent
    from sqlalchemy import delete, select

    async with session_factory()() as session:
        rows = (
            await session.execute(select(Agent).where(Agent.name.like(f"{MARKER}%")))
        ).scalars().all()
        ids = [a.agent_id for a in rows]
        await session.execute(delete(Agent).where(Agent.agent_id.in_(ids)))
        await session.commit()
    for i, agent_id in enumerate(ids):
        await mark_absent(SPACES[i % len(SPACES)], agent_id)
    print(f"cleared {len(ids)} synthetic agents")


async def main() -> None:
    from agora_api.db import dispose_engine
    from agora_api.ratelimit import close_redis

    try:
        command = sys.argv[1] if len(sys.argv) > 1 else "clear"
        if command == "seed":
            await seed(int(sys.argv[2]))
        else:
            await clear()
    finally:
        await close_redis()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
