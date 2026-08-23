"""Sprint 05.1 performance baseline (S5.1-T10/T11/T12).

Seeds 250 Missions, 5000 MissionTasks, ~7000 dependency edges, 1000
Artifacts, 2000 ArtifactVersions and 3000 ArtifactReviews directly into
Postgres (no crypto, no Bridge, no model calls), then benchmarks the read
and write paths a coordinator/Mission Board actually exercises, plus
streaming upload/download throughput and memory behavior at 1/10/100 MB.

Run: .venv/bin/python scripts/mission_scale_harness.py

Never run against a database you care about: everything is deterministic
synthetic data namespaced under one throwaway Agent, safely dropped by
re-running the fresh-bootstrap procedure in the completion report.
"""

import asyncio
import hashlib
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

# Never let this harness write synthetic blobs into the real local owner's
# ~/.agora/artifact-store — isolate under a throwaway temp dir, same fix as
# tests/conftest.py.
os.environ.setdefault(
    "AGORA_ARTIFACT_STORE_ROOT", tempfile.mkdtemp(prefix="agora-bench-artifacts-")
)

N_MISSIONS = 250
N_TASKS = 5000
N_ARTIFACTS = 1000
N_VERSIONS = 2000
N_REVIEWS = 3000


def pctl(values: list[float], p: float) -> float:
    return sorted(values)[max(0, int(len(values) * p) - 1)]


async def seed() -> dict:
    from agora_api.artifact_store import LocalArtifactStore
    from agora_api.config import get_settings
    from agora_api.db import session_factory
    from agora_api.events import now_utc
    from agora_api.ids import (
        new_agent_id,
        new_artifact_id,
        new_artifact_version_id,
        new_mission_id,
        new_mission_task_id,
        new_review_id,
    )
    from agora_api.models import (
        Agent,
        Artifact,
        ArtifactReview,
        ArtifactVersion,
        Mission,
        MissionTask,
        MissionTaskDependency,
    )

    async with session_factory()() as session:
        agent_id = new_agent_id()
        session.add(Agent(agent_id=agent_id, name=f"ScaleAgent-{secrets.token_hex(4)}",
                          status="registered", created_at=now_utc(), updated_at=now_utc()))
        await session.flush()

        mission_ids = []
        for i in range(N_MISSIONS):
            mid = new_mission_id()
            mission_ids.append(mid)
            session.add(Mission(
                mission_id=mid, title=f"Synthetic mission {i}", objective="scale test",
                state="active", visibility="public", max_participants=16,
                completion_policy={}, created_by_agent_id=agent_id, created_at=now_utc(),
            ))
        await session.flush()

        task_ids = []
        for i in range(N_TASKS):
            tid = new_mission_task_id()
            task_ids.append(tid)
            session.add(MissionTask(
                mission_task_id=tid, mission_id=mission_ids[i % N_MISSIONS],
                title=f"Synthetic task {i}", description="scale test", state="ready",
                attempt=0, created_at=now_utc(), updated_at=now_utc(),
            ))
        await session.flush()

        n_edges = 0
        target_edges = 7000
        for i in range(N_TASKS):
            if n_edges >= target_edges:
                break
            same_mission_offset = i - (i % 20) - 1  # a nearby, earlier task in the same block
            if same_mission_offset < 0 or same_mission_offset == i:
                continue
            if task_ids[same_mission_offset] == task_ids[i]:
                continue
            session.add(MissionTaskDependency(
                task_id=task_ids[i], depends_on_task_id=task_ids[same_mission_offset]
            ))
            n_edges += 1
        await session.flush()

        artifact_ids = []
        for i in range(N_ARTIFACTS):
            aid = new_artifact_id()
            artifact_ids.append(aid)
            session.add(Artifact(
                artifact_id=aid, title=f"Synthetic artifact {i}", artifact_type="report",
                visibility="public", created_by_agent_id=agent_id, latest_version_number=0,
                created_at=now_utc(),
            ))
        await session.flush()

        store = LocalArtifactStore(Path(get_settings().artifact_store_root).expanduser())
        version_ids = []
        for i in range(N_VERSIONS):
            content = f"synthetic artifact version {i}".encode()
            content_hash = hashlib.sha256(content).hexdigest()
            store_path = store._final_path(content_hash)  # noqa: SLF001 - harness-only shortcut
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store_path.write_bytes(content)
            vid = new_artifact_version_id()
            version_ids.append(vid)
            artifact_id = artifact_ids[i % N_ARTIFACTS]
            session.add(ArtifactVersion(
                artifact_version_id=vid, artifact_id=artifact_id,
                version_number=1 + i // N_ARTIFACTS,
                state="published", created_by_agent_id=agent_id, content_hash=content_hash,
                content_size=len(content), media_type="text/plain",
                storage_key=f"sha256/{content_hash[:2]}/{content_hash}",
                provenance_manifest={"artifact_version_id": vid, "content_hash": content_hash},
                created_at=now_utc(), published_at=now_utc(),
            ))
        await session.flush()

        for i in range(N_REVIEWS):
            session.add(ArtifactReview(
                review_id=new_review_id(), artifact_version_id=version_ids[i % N_VERSIONS],
                reviewer_agent_id=agent_id, verdict=["approve", "needs_changes", "reject"][i % 3],
                is_self_review=False, created_at=now_utc(),
            ))
        await session.commit()

    return {
        "agent_id": agent_id, "sample_mission_id": mission_ids[0],
        "sample_task_id": task_ids[0], "sample_artifact_id": artifact_ids[0],
        "sample_version_id": version_ids[0],
    }


def _rss_mb(pid: int) -> float:
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


async def main() -> None:
    from agora_api.db import dispose_engine
    from agora_api.ratelimit import close_redis

    print("== AGORA Mission/Artifact scale harness ==")
    t0 = time.perf_counter()
    seeded = await seed()
    print(f"seeded {N_MISSIONS} missions, {N_TASKS} tasks, {N_ARTIFACTS} artifacts, "
          f"{N_VERSIONS} versions, {N_REVIEWS} reviews in {time.perf_counter()-t0:.1f}s")
    await close_redis()
    await dispose_engine()

    port_env = os.environ.copy()
    port_env["AGORA_RATELIMIT_MAX_REQUESTS"] = "1000000"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agora_api.main:app", "--port", str(port),
         "--log-level", "error"],
        cwd=REPO, env=port_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60)
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

        mission_id = seeded["sample_mission_id"]
        artifact_id = seeded["sample_artifact_id"]

        bench("mission list (50/page)", lambda: client.get("/v1/missions?limit=50"))
        bench("mission detail", lambda: client.get(f"/v1/missions/{mission_id}"))
        bench("mission task DAG (tasks list)",
              lambda: client.get(f"/v1/missions/{mission_id}/tasks"))
        bench("artifact detail (with versions)",
              lambda: client.get(f"/v1/artifacts/{artifact_id}"))

        # Transactional task claim p50/p95 needs a REAL agent+session per
        # attempt (claim is per-agent authenticated) — register once, then
        # repeatedly claim/expire-back-to-ready synthetic tasks.
        import base64

        from agora_api.crypto import registration_message
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        priv = Ed25519PrivateKey.generate()
        pub_b64 = base64.urlsafe_b64encode(
            priv.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode().rstrip("=")
        name = f"BenchAgent-{secrets.token_hex(4)}"
        ch = client.post("/v1/registration/challenge",
                         json={"public_key": pub_b64, "agent_name": name}).json()
        msg = registration_message(ch["challenge_id"], ch["nonce"], pub_b64, name)
        sig = base64.urlsafe_b64encode(priv.sign(msg)).decode().rstrip("=")
        reg = client.post("/v1/registration/register", json={
            "challenge_id": ch["challenge_id"], "public_key": pub_b64, "agent_name": name,
            "signature": sig, "idempotency_key": f"bench-{secrets.token_hex(4)}",
        }).json()
        auth = {"Authorization": f"Bearer {reg['session_token']}"}

        bench_mission = client.post(
            "/v1/missions", json={"title": "bench", "objective": "bench"}, headers=auth
        ).json()
        claim_times, renew_times = [], []
        for i in range(30):
            t = client.post(
                f"/v1/missions/{bench_mission['mission_id']}/tasks",
                json={"title": f"bt{i}", "description": "bench"}, headers=auth,
            ).json()
            t0c = time.perf_counter()
            claimed = client.post(f"/v1/mission-tasks/{t['mission_task_id']}/claim", headers=auth)
            assert claimed.status_code == 200
            claim_times.append((time.perf_counter() - t0c) * 1000)
            t0r = time.perf_counter()
            renewed = client.post(
                f"/v1/mission-tasks/{t['mission_task_id']}/renew-lease", headers=auth
            )
            assert renewed.status_code == 200
            renew_times.append((time.perf_counter() - t0r) * 1000)
        print(f"transactional task claim: p50 {pctl(claim_times,0.5):.1f} ms · "
              f"p95 {pctl(claim_times,0.95):.1f} ms")
        print(f"lease renewal: p50 {pctl(renew_times,0.5):.1f} ms · "
              f"p95 {pctl(renew_times,0.95):.1f} ms")

        # Mission completion evaluator: single-task mission, accept it.
        completion_times = []
        for _i in range(10):
            m = client.post(
                "/v1/missions", json={"title": "c", "objective": "c"}, headers=auth
            ).json()
            client.post(f"/v1/missions/{m['mission_id']}/activate", headers=auth)
            t = client.post(
                f"/v1/missions/{m['mission_id']}/tasks",
                json={"title": "only", "description": "c"}, headers=auth,
            ).json()
            client.post(f"/v1/mission-tasks/{t['mission_task_id']}/claim", headers=auth)
            client.post(f"/v1/mission-tasks/{t['mission_task_id']}/submit", json={}, headers=auth)
            t0e = time.perf_counter()
            accepted = client.post(f"/v1/mission-tasks/{t['mission_task_id']}/accept", headers=auth)
            assert accepted.status_code == 200
            completion_times.append((time.perf_counter() - t0e) * 1000)
        print(f"completion evaluation (on accept, incl. eval): "
              f"p50 {pctl(completion_times,0.5):.1f} ms · p95 {pctl(completion_times,0.95):.1f} ms")

        # Streaming upload/download at 1/10/100 MB.
        art = client.post(
            "/v1/artifacts", json={"title": "upload-bench", "artifact_type": "dataset"},
            headers=auth,
        ).json()
        for size_mb in (1, 10, 100):
            payload = os.urandom(size_mb * 1024 * 1024)
            t0u = time.perf_counter()
            up = client.post(
                f"/v1/artifacts/{art['artifact_id']}/versions",
                files={"file": (f"blob-{size_mb}mb.bin", payload, "application/octet-stream")},
                data={"metadata": "{}"}, headers=auth,
            )
            up_elapsed = time.perf_counter() - t0u
            assert up.status_code == 201, up.text
            version_id = up.json()["artifact_version_id"]
            throughput_up = size_mb / up_elapsed
            t0d = time.perf_counter()
            down = client.get(f"/v1/artifact-versions/{version_id}/download")
            down_elapsed = time.perf_counter() - t0d
            assert down.status_code == 200
            throughput_down = size_mb / down_elapsed
            print(f"{size_mb} MB upload: {up_elapsed*1000:.0f} ms ({throughput_up:.1f} MB/s), "
                  f"API RSS {_rss_mb(api.pid):.0f} MB | download: {down_elapsed*1000:.0f} ms "
                  f"({throughput_down:.1f} MB/s)")

        # Dedup ratio: publish identical content twice, confirm one blob.
        dup_content = os.urandom(1024 * 1024)
        first = client.post(
            f"/v1/artifacts/{art['artifact_id']}/versions",
            files={"file": ("dup.bin", dup_content, "application/octet-stream")},
            data={"metadata": "{}"}, headers=auth,
        ).json()
        second = client.post(
            f"/v1/artifacts/{art['artifact_id']}/versions",
            files={"file": ("dup2.bin", dup_content, "application/octet-stream")},
            data={"metadata": "{}"}, headers=auth,
        ).json()
        same_blob = first["content_hash"] == second["content_hash"]
        print(f"content-addressed dedup: two identical uploads -> same blob = {same_blob}")

        pg_size = subprocess.run(
            ["docker", "exec", "agora-dev-postgres-1", "psql", "-U", "agora", "-d", "agora",
             "-tc", "SELECT pg_size_pretty(pg_database_size('agora'))"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        print(f"PostgreSQL database size: {pg_size}")
        print(f"final API RSS: {_rss_mb(api.pid):.0f} MB")
        print("== harness complete ==")
    finally:
        api.terminate()
        api.wait(timeout=10)


if __name__ == "__main__":
    asyncio.run(main())
