"""Sprint 04 performance baseline (S4-T22).

Seeds 1000 Claims, 2000 ClaimRelations, 1500 Evidence objects, 100 Debates
and 5000 AudienceAssessments directly into Postgres (no crypto, no Bridge,
no model calls — a pure data scale test), then benchmarks the read paths a
browser/agent actually exercises.

Run: .venv/bin/python scripts/epistemic_scale_harness.py
"""

import asyncio
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

PLAZA = "spc_00000000000000000000P1AZA0"


def pctl(values: list[float], p: float) -> float:
    return sorted(values)[max(0, int(len(values) * p) - 1)]


async def seed(n_claims: int, n_relations: int, n_evidence: int, n_debates: int,
               n_assessments: int) -> dict:
    from agora_api.db import session_factory
    from agora_api.events import now_utc
    from agora_api.ids import (
        new_agent_id,
        new_claim_id,
        new_debate_id,
        new_evidence_id,
        new_position_id,
        new_relation_id,
    )
    from agora_api.models import (
        Agent,
        AudienceAssessment,
        Claim,
        ClaimEvidence,
        ClaimRelation,
        Debate,
        DebatePosition,
        Evidence,
    )

    claim_types = ["observation", "fact_claim", "hypothesis", "forecast"]
    relation_types = ["supports", "contradicts", "qualifies", "cites"]

    async with session_factory()() as session:
        agent_id = new_agent_id()
        session.add(Agent(agent_id=agent_id, name=f"ScaleAgent-{secrets.token_hex(4)}",
                          status="registered", created_at=now_utc(), updated_at=now_utc()))
        await session.flush()

        claim_ids = []
        for i in range(n_claims):
            cid = new_claim_id()
            claim_ids.append(cid)
            session.add(Claim(
                claim_id=cid, space_id=PLAZA, author_agent_id=agent_id,
                claim_type=claim_types[i % len(claim_types)],
                text=f"Synthetic claim {i} for scale testing.", status="active",
                created_at=now_utc(),
            ))
        await session.flush()

        evidence_ids = []
        for i in range(n_evidence):
            eid = new_evidence_id()
            evidence_ids.append(eid)
            session.add(Evidence(
                evidence_id=eid, source_type="url", locator=f"https://example.org/e{i}",
                provenance_level="reference_only", created_by_agent_id=agent_id,
                created_at=now_utc(),
            ))
        await session.flush()  # evidence rows exist before any attachment references them
        for i in range(min(n_evidence, n_claims)):
            session.add(ClaimEvidence(
                attachment_id=new_evidence_id(), claim_id=claim_ids[i % n_claims],
                evidence_id=evidence_ids[i], role="supports", attached_by_agent_id=agent_id,
                created_at=now_utc(),
            ))
        await session.flush()

        seen_edges = set()
        for i in range(n_relations):
            source = claim_ids[i % n_claims]
            target = claim_ids[(i * 7 + 3) % n_claims]
            if source == target:
                continue
            relation_type = relation_types[(i + i // n_claims) % len(relation_types)]
            edge = (source, target, relation_type)
            if edge in seen_edges:
                continue  # partial unique index: one active edge per author
            seen_edges.add(edge)
            session.add(ClaimRelation(
                relation_id=new_relation_id(), source_claim_id=source, target_claim_id=target,
                relation_type=relation_type,
                author_agent_id=agent_id, status="active", created_at=now_utc(),
            ))

        debate_ids = []
        for i in range(n_debates):
            did = new_debate_id()
            debate_ids.append(did)
            session.add(Debate(
                debate_id=did, space_id=PLAZA, question=f"Synthetic debate {i}?",
                status="open", max_participants=2, created_by_agent_id=agent_id,
                created_at=now_utc(),
            ))
            session.add(DebatePosition(position_id=new_position_id(), debate_id=did,
                                       name="YES", sort_order=0))
            session.add(DebatePosition(position_id=new_position_id(), debate_id=did,
                                       name="NO", sort_order=1))
        await session.flush()

        for i in range(n_assessments):
            debate_id = debate_ids[i % n_debates]
            session.add(AudienceAssessment(
                debate_id=debate_id, assessor_kind="agent" if i % 2 else "human",
                assessor_id=f"scale-assessor-{i}",
                evidence_quality=1 + i % 5, clarity=1 + (i * 3) % 5,
                responsiveness=1 + (i * 7) % 5, updated_at=now_utc(),
            ))
        await session.commit()

    return {"agent_id": agent_id, "sample_claim": claim_ids[0], "sample_debate": debate_ids[0],
            "claim_ids": claim_ids}


async def main() -> None:
    from agora_api.db import dispose_engine
    from agora_api.ratelimit import close_redis

    print("== AGORA epistemic scale harness ==")
    t0 = time.perf_counter()
    seeded = await seed(1000, 2000, 1500, 100, 5000)
    print(f"seeded 1000 claims, ~2000 relations, 1500 evidence, 100 debates, "
          f"5000 assessments in {time.perf_counter()-t0:.1f}s")
    await close_redis()
    await dispose_engine()

    port_env = os.environ.copy()
    port_env["AGORA_RATELIMIT_MAX_REQUESTS"] = "1000000"
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agora_api.main:app", "--port", str(port),
         "--log-level", "error"],
        cwd=REPO, env=port_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)
    try:
        for _ in range(80):
            try:
                if client.get("/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)

        def bench(label: str, fn, n: int = 30) -> None:
            times = []
            for _ in range(n):
                t = time.perf_counter()
                r = fn()
                assert r.status_code == 200, r.text
                times.append((time.perf_counter() - t) * 1000)
            print(f"{label}: p50 {pctl(times,0.5):.1f} ms · p95 {pctl(times,0.95):.1f} ms")

        claim_id = seeded["sample_claim"]
        debate_id = seeded["sample_debate"]
        bench("claim list (Space, 50/page)",
              lambda: client.get(f"/v1/spaces/{PLAZA}/claims?limit=50"))
        bench("claim detail", lambda: client.get(f"/v1/claims/{claim_id}"))
        bench("graph depth=1", lambda: client.get(f"/v1/claims/{claim_id}/neighborhood?depth=1"))
        bench("graph depth=2", lambda: client.get(f"/v1/claims/{claim_id}/neighborhood?depth=2"))
        bench("audience assessment-summary",
              lambda: client.get(f"/v1/debates/{debate_id}/assessment-summary"))

        import json as jsonlib

        neighborhood = client.get(f"/v1/claims/{claim_id}/neighborhood?depth=2").json()
        print(f"depth=2 neighborhood size: {len(neighborhood['claims'])} claims, "
              f"{len(neighborhood['relations'])} relations, truncated={neighborhood['truncated']}")
        print(f"neighborhood payload: {len(jsonlib.dumps(neighborhood))} bytes")

        pg_size = subprocess.run(
            ["docker", "exec", "agora-dev-postgres-1", "psql", "-U", "agora", "-d", "agora",
             "-tc", "SELECT pg_size_pretty(pg_database_size('agora'))"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        print(f"PostgreSQL database size: {pg_size}")
        print(f"API RSS: {_rss_mb(api.pid):.0f} MB")
        print("== harness complete ==")
    finally:
        api.terminate()
        api.wait(timeout=10)


def _rss_mb(pid: int) -> float:
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


if __name__ == "__main__":
    asyncio.run(main())
