"""Sprint 03 world scale harness (S3-T24/T25).

Synthetic presence: seeds N agents directly into Postgres + Redis so 1000
"inhabitants" cost zero Bridge processes and zero model calls. Then measures
what the browser would actually consume, by driving the real page through
the preview browser is left to the E2E; here we measure the SERVER side and
the payload volume the client must process:

  - population endpoint latency and payload size at 100/500/1000
  - world manifest size (downloaded once, then 304)
  - realtime bytes for one semantic transition
  - Event Ledger growth during idle rendering (must be zero)
  - backend RSS / Redis footprint

Run:  .venv/bin/python scripts/world_scale_harness.py
"""

import asyncio
import json
import os
import secrets
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

PLAZA = "spc_00000000000000000000P1AZA0"
SPACES = [
    PLAZA,
    "spc_0000000000000000000SCIENCE",
    "spc_0000000000000000000ECONOMY",
    "spc_00000000000000000000GARDEN",
    "spc_000000000000000000000FORGE",
    "spc_0000000000000000000UNKNOWN",
]
SIZES = [int(x) for x in os.environ.get("HARNESS_SIZES", "100,500,1000").split(",")]


def free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rss_mb(pid: int) -> float:
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


def pctl(values, p):
    return sorted(values)[max(0, int(len(values) * p) - 1)]


async def seed_synthetic(count: int) -> list[str]:
    """Insert agents + Redis presence without any Bridge or crypto work."""
    from agora_api.avatars import default_avatar
    from agora_api.db import session_factory
    from agora_api.events import now_utc
    from agora_api.ids import new_agent_id
    from agora_api.models import Agent
    from agora_api.presence import mark_present

    activities = ["idle", "reading", "discussing", "researching", "computing", "building"]
    ids: list[str] = []
    async with session_factory()() as session:
        for i in range(count):
            agent_id = new_agent_id()
            ids.append(agent_id)
            session.add(Agent(
                agent_id=agent_id,
                name=f"Synthetic-{secrets.token_hex(3)}-{i}",
                status="registered",
                avatar=default_avatar(agent_id),
                activity=activities[i % len(activities)],
                created_at=now_utc(),
                updated_at=now_utc(),
            ))
        await session.commit()
    for i, agent_id in enumerate(ids):
        await mark_present(SPACES[i % len(SPACES)], agent_id, f"Synthetic-{i}")
    return ids


async def clear_synthetic(ids: list[str]) -> None:
    from agora_api.db import session_factory
    from agora_api.models import Agent
    from agora_api.presence import mark_absent
    from sqlalchemy import delete

    for i, agent_id in enumerate(ids):
        await mark_absent(SPACES[i % len(SPACES)], agent_id)
    async with session_factory()() as session:
        await session.execute(delete(Agent).where(Agent.agent_id.in_(ids)))
        await session.commit()


async def main() -> None:
    port = free_port()
    env = os.environ.copy()
    env["AGORA_RATELIMIT_MAX_REQUESTS"] = "1000000"
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agora_api.main:app", "--port", str(port),
         "--log-level", "error"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    client = httpx.Client(base_url=base, timeout=60)
    seeded: list[str] = []
    try:
        for _ in range(80):
            try:
                if client.get("/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)

        manifest = client.get("/v1/world/manifest")
        manifest_bytes = len(manifest.content)
        etag = manifest.headers["etag"]
        revalidate = client.get("/v1/world/manifest", headers={"If-None-Match": etag})
        print("== AGORA world scale harness ==")
        print(f"world manifest: {manifest_bytes} bytes once, "
              f"revalidation -> {revalidate.status_code} ({len(revalidate.content)} bytes)")

        for size in SIZES:
            new_ids = await seed_synthetic(size - len(seeded))
            seeded.extend(new_ids)

            times, payload = [], 0
            for _ in range(15):
                t0 = time.perf_counter()
                response = client.get("/v1/world/population")
                times.append((time.perf_counter() - t0) * 1000)
                payload = len(response.content)
            print(f"\n-- {size} synthetic agents --")
            print(f"population endpoint: p50 {pctl(times,0.5):.1f} ms · "
                  f"p95 {pctl(times,0.95):.1f} ms · avg {statistics.mean(times):.1f} ms")
            print(f"snapshot payload: {payload/1024:.1f} KB "
                  f"({payload/max(size,1):.0f} bytes/agent)")

            data = client.get("/v1/world/population").json()
            print(f"total_present reported: {data['total_present']}")

        # Idle-render invariant: no ledger writes while a browser just renders.
        from agora_api.db import session_factory
        from agora_api.models import Event
        from sqlalchemy import func, select

        async with session_factory()() as session:
            before = (await session.execute(select(func.count()).select_from(Event))).scalar_one()
        for _ in range(20):
            client.get("/v1/world/population")
            client.get("/v1/world/manifest", headers={"If-None-Match": etag})
        async with session_factory()() as session:
            after = (await session.execute(select(func.count()).select_from(Event))).scalar_one()
        print(f"\nledger rows created by 40 idle render-support requests: {after - before}")

        redis_info = subprocess.run(
            ["docker", "exec", "agora-dev-redis-1", "redis-cli", "info", "memory"],
            capture_output=True, text=True, check=False).stdout
        used = next((line.split(":")[1].strip() for line in redis_info.splitlines()
                     if line.startswith("used_memory_human")), "?")
        print(f"redis used_memory with {len(seeded)} present: {used}")
        print(f"api RSS: {rss_mb(api.pid):.0f} MB")

        # One semantic transition's realtime payload (what a mover costs).
        frame = {
            "scope": PLAZA, "kind": "presence",
            "data": {"event": "transition", "agent_id": seeded[0],
                     "name": "Synthetic-0", "from_space_id": PLAZA,
                     "to_space_id": SPACES[1], "activity": "exploring",
                     "avatar": {"schema_version": "1.0", "body": "orb", "visor": "round",
                                "antenna": "none", "accessory": "none", "emblem": "none",
                                "expression": "neutral", "tint": "#4ac48a"},
                     "at": "2026-08-22T00:00:00Z"},
        }
        print(f"bytes per semantic transition frame: {len(json.dumps(frame))}")
        print("\n== harness complete ==")
    finally:
        if seeded:
            await clear_synthetic(seeded)
        from agora_api.db import dispose_engine
        from agora_api.ratelimit import close_redis

        await close_redis()
        await dispose_engine()
        api.terminate()
        api.wait(timeout=10)


if __name__ == "__main__":
    asyncio.run(main())
