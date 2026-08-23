"""Ephemeral presence (S2-T07, ADR-0012).

Presence lives ONLY in Redis with TTLs — never in the immutable ledger.
- key `presence:{space_id}:{agent_id}` → JSON blob, TTL PRESENCE_TTL.
- Bridges heartbeat every HEARTBEAT_INTERVAL seconds over their realtime
  connection; each heartbeat refreshes the TTL.
- A crashed Bridge simply stops refreshing and expires to offline after
  PRESENCE_TTL — no database repair, no cleanup job needed.
Semantically meaningful transitions (explicit enter/leave) DO append ledger
events; TTL expiry does not (it is an inference, not an action).
"""

import json

from agora_api.events import now_utc
from agora_api.ratelimit import get_redis

HEARTBEAT_INTERVAL = 10  # seconds, Bridge-side send cadence
PRESENCE_TTL = 30  # seconds, 3 missed heartbeats → offline


def _key(space_id: str, agent_id: str) -> str:
    return f"presence:{space_id}:{agent_id}"


async def mark_present(space_id: str, agent_id: str, agent_name: str | None = None) -> None:
    payload = json.dumps(
        {"agent_id": agent_id, "name": agent_name, "since": now_utc().isoformat()}
    )
    await get_redis().set(_key(space_id, agent_id), payload, ex=PRESENCE_TTL)
    await get_redis().set(f"presence:agent:{agent_id}", space_id, ex=PRESENCE_TTL)


async def refresh_presence(agent_id: str) -> None:
    """Heartbeat: refresh whatever space the agent currently occupies."""
    r = get_redis()
    space_id = await r.get(f"presence:agent:{agent_id}")
    if space_id:
        await r.expire(_key(space_id, agent_id), PRESENCE_TTL)
        await r.expire(f"presence:agent:{agent_id}", PRESENCE_TTL)


async def mark_absent(space_id: str, agent_id: str) -> None:
    r = get_redis()
    await r.delete(_key(space_id, agent_id))
    await r.delete(f"presence:agent:{agent_id}")


async def list_present(space_id: str) -> list[dict]:
    r = get_redis()
    agents = []
    async for key in r.scan_iter(match=f"presence:{space_id}:*", count=200):
        raw = await r.get(key)
        if raw:
            agents.append(json.loads(raw))
    return sorted(agents, key=lambda a: a["agent_id"])


async def current_space(agent_id: str) -> str | None:
    return await get_redis().get(f"presence:agent:{agent_id}")
