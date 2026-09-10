"""Provider-free protocol measurement. Run only via run-load-isolated.py.

Counts verified outcomes, not submitted requests. No inference or economic actions.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import math
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import httpx
import websockets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[1]
PLAZA = "spc_00000000000000000000P1AZA0"


def require_isolation(env):
    """Refuse defaults/live addresses before opening connections or spawning API."""
    run = env.get("AGORA_RUN_ID", "")
    db = urlparse(env.get("AGORA_DATABASE_URL", ""))
    if not re.fullmatch(r"load_[a-f0-9]{16}", run):
        raise ValueError("unique isolated harness run ID required")
    if db.path != f"/agora_test_{run}" or db.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("dedicated local harness database required")
    for key, forbidden in [("AGORA_REDIS_URL", 6380), ("AGORA_NATS_URL", 4222)]:
        parsed = urlparse(env.get(key, ""))
        if parsed.hostname != "127.0.0.1" or not parsed.port or parsed.port == forbidden:
            raise ValueError("dedicated local broker endpoint required")
    required = {
        "AGORA_ENV": "test",
        "AGORA_PROVENANCE_CLASS": "test",
        "AGORA_OUTBOX_ENABLED": "false",
        "AGORA_RESEARCH_SCHEDULER_ENABLED": "false",
        "AGORA_ENVIRONMENT_ID": run,
        "AGORA_TEST_WORLD_INSTANCE_ID": run,
    }
    if any(env.get(k) != v for k, v in required.items()):
        raise ValueError("isolated TEST environment required")
    marker = Path(env.get("AGORA_ARTIFACT_STORE_ROOT", "/nonexistent")) / ".harness-owner"
    if not marker.is_file() or marker.read_text().strip() != run:
        raise ValueError("owned temporary artifact directory required")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


def latency(values):
    return {
        "count": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
    }


def checked(response, *, rpc=False):
    if not 200 <= response.status_code < 300:
        raise ValueError(f"HTTP request rejected: {response.status_code}")
    body = response.json()
    if not isinstance(body, dict) or "error" in body:
        raise ValueError("response contains application/RPC error")
    if rpc and (body.get("jsonrpc") != "2.0" or "result" not in body):
        raise ValueError("invalid JSON-RPC result")
    return body


def b64url(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


async def register(client):
    private = Ed25519PrivateKey.generate()
    public = b64url(
        private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    )
    name = f"TEST-load-{secrets.token_hex(5)}"
    challenge = checked(
        await client.post(
            "/v1/registration/challenge", json={"public_key": public, "agent_name": name}
        )
    )
    message = (
        f"agora.register.v1|{challenge['challenge_id']}|{challenge['nonce']}|{public}|{name}"
    ).encode()
    reg = checked(
        await client.post(
            "/v1/registration/register",
            json={
                "challenge_id": challenge["challenge_id"],
                "public_key": public,
                "agent_name": name,
                "signature": b64url(private.sign(message)),
                "idempotency_key": secrets.token_hex(16),
            },
        )
    )
    rules = checked(await client.get("/v1/world/rules"))
    checked(
        await client.post(
            "/v1/world/rules/attest",
            headers=auth(reg),
            json={"rules_version": rules["rules_version"], "answers": rules["entry_test"]},
        )
    )
    return reg


def auth(reg):
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def receive(ws, kind, *, task_id=None, timeout=15):
    async with asyncio.timeout(timeout):
        while True:
            frame = json.loads(await ws.recv())
            if frame.get("type") in {"revoked", "a2a_result_rejected"}:
                raise ValueError("websocket operation rejected")
            if frame.get("type") == kind and (task_id is None or frame.get("task_id") == task_id):
                return frame


async def event_count(db):
    return await db.fetchval("SELECT count(*) FROM events")


async def run(output):
    require_isolation(os.environ)
    n = int(os.environ.get("HARNESS_CONNECTIONS", "2"))
    rounds = int(os.environ.get("HARNESS_HEARTBEAT_ROUNDS", "2"))
    messages = int(os.environ.get("HARNESS_MESSAGES", "2"))
    tasks = int(os.environ.get("HARNESS_TASKS", "1"))
    if (
        not 2 <= n <= 500
        or not 1 <= rounds <= 1000
        or not 1 <= messages <= 1000
        or not 1 <= tasks <= 100
    ):
        raise ValueError("harness workload outside explicit limits")
    db = await asyncpg.connect(
        os.environ["AGORA_DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    )
    actual_db = await db.fetchval("SELECT current_database()")
    if actual_db != "agora_test_" + os.environ["AGORA_RUN_ID"]:
        await db.close()
        raise ValueError("connected database identity mismatch")
    port = free_port()
    report = {
        "classification": "TEST_ONLY_PROVIDER_FREE_PROTOCOL_SMOKE",
        "run_id": os.environ["AGORA_RUN_ID"],
        "connections_requested": n,
        "provider_calls": 0,
        "economic_actions": 0,
        "errors": [],
        "status": "FAIL",
        "limits": [
            "single API process, local host",
            "no paid model execution",
            "not a sustained capacity or production SLO benchmark",
            "default rate limits overridden only inside isolated environment",
        ],
    }
    sockets = []
    env = dict(os.environ, AGORA_RATELIMIT_MAX_REQUESTS="100000")
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "agora_api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
            ready = False
            for _ in range(120):
                if api.poll() is not None:
                    raise ValueError("isolated API exited before readiness")
                try:
                    checked(await client.get("/healthz"))
                    ready = True
                    break
                except (httpx.HTTPError, ValueError):
                    await asyncio.sleep(0.25)
            if not ready:
                raise TimeoutError("isolated API readiness timeout")
            regs = [await register(client) for _ in range(n)]
            report["registrations_attested"] = len(regs)
            connect_times = []

            async def connect(reg):
                before = time.perf_counter()
                ws = await websockets.connect(
                    f"ws://127.0.0.1:{port}/v1/realtime/bridge",
                    additional_headers=auth(reg),
                    open_timeout=30,
                )
                sockets.append(ws)
                frame = await receive(ws, "welcome")
                if frame.get("agent_id") != reg["agent_id"]:
                    raise ValueError("welcome identity mismatch")
                await ws.send(
                    json.dumps({"type": "bridge_capabilities", "a2a_delivery_protocol": 2})
                )
                capability = await receive(ws, "bridge_capabilities_ack")
                if capability.get("a2a_delivery_protocol") != 2:
                    raise ValueError("Bridge delivery protocol negotiation failed")
                connect_times.append((time.perf_counter() - before) * 1000)
                return ws

            ordered_sockets = await asyncio.gather(*(connect(reg) for reg in regs))
            report["connection_establishment"] = latency(connect_times)
            expected = {reg["agent_id"] for reg in regs}
            before = time.perf_counter()
            for reg in regs:
                checked(await client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth(reg)))
            async with asyncio.timeout(15):
                while True:
                    present = checked(await client.get(f"/v1/spaces/{PLAZA}/agents"))["agents"]
                    if expected <= {row["agent_id"] for row in present}:
                        break
                    await asyncio.sleep(0.05)
            report["presence_verified"] = n
            report["enter_and_presence_readback_ms"] = (time.perf_counter() - before) * 1000
            # Baseline after all explicit entry operations; exact SQL, not a paginated event page.
            events_before = await event_count(db)
            hb_times = []

            async def heartbeat(ws):
                before = time.perf_counter()
                await ws.send(json.dumps({"type": "heartbeat"}))
                await receive(ws, "heartbeat_ack")
                hb_times.append((time.perf_counter() - before) * 1000)

            for _ in range(rounds):
                await asyncio.gather(*(heartbeat(ws) for ws in ordered_sockets))
            report["heartbeat_acknowledged"] = latency(hb_times)
            report["heartbeat_event_delta"] = await event_count(db) - events_before
            if report["heartbeat_event_delta"] != 0:
                raise ValueError("heartbeat phase unexpectedly wrote durable events")
            msg_times = []
            for i in range(messages):
                before = time.perf_counter()
                body = checked(
                    await client.post(
                        f"/v1/spaces/{PLAZA}/messages",
                        json={"content": f"TEST protocol smoke {i}"},
                        headers=auth(regs[0]),
                    )
                )
                rows = checked(
                    await client.get(f"/v1/spaces/{PLAZA}/messages", params={"limit": 100})
                )["messages"]
                if (
                    not body.get("event_id")
                    or sum(row["message_id"] == body["message_id"] for row in rows) != 1
                ):
                    raise ValueError("message receipt missing or duplicate")
                msg_times.append((time.perf_counter() - before) * 1000)
            report["message_write_and_readback"] = latency(msg_times)
            a2a_times = []
            for i in range(tasks):
                before = time.perf_counter()
                route = f"/v1/a2a/agents/{regs[1]['agent_id']}/jsonrpc"
                request = {
                    "jsonrpc": "2.0",
                    "id": i,
                    "method": "message/send",
                    "params": {
                        "message": {
                            "messageId": secrets.token_hex(16),
                            "role": "ROLE_USER",
                            "parts": [{"text": "TEST deterministic fixture, no provider"}],
                        }
                    },
                }
                body = checked(
                    await client.post(route, json=request, headers=auth(regs[0])), rpc=True
                )
                task_id = body["result"]["task"]["id"]
                await receive(ordered_sockets[1], "a2a_task", task_id=task_id)
                execution_id = str(uuid.uuid4())
                await ordered_sockets[1].send(
                    json.dumps(
                        {
                            "type": "a2a_task_claim",
                            "task_id": task_id,
                            "execution_id": execution_id,
                        }
                    )
                )
                claimed = await receive(ordered_sockets[1], "a2a_task_claim_ack", task_id=task_id)
                if (
                    claimed.get("accepted") is not True
                    or claimed.get("execution_id") != execution_id
                ):
                    raise ValueError("A2A execution claim rejected")
                await ordered_sockets[1].send(
                    json.dumps(
                        {
                            "type": "a2a_result",
                            "execution_id": execution_id,
                            "task_id": task_id,
                            "status": "completed",
                            "artifacts": [
                                {
                                    "artifactId": f"fixture-{i}",
                                    "name": "TEST deterministic fixture",
                                    "parts": [{"text": "fixture-complete"}],
                                }
                            ],
                        }
                    )
                )
                await receive(ordered_sockets[1], "a2a_result_ack", task_id=task_id)
                poll = checked(
                    await client.post(
                        route,
                        headers=auth(regs[0]),
                        json={
                            "jsonrpc": "2.0",
                            "id": i + 1000,
                            "method": "tasks/get",
                            "params": {"id": task_id},
                        },
                    ),
                    rpc=True,
                )
                task = poll["result"]["task"]
                if task.get("status", {}).get("state") not in {
                    "TASK_STATE_COMPLETED",
                    "completed",
                } or not task.get("artifacts"):
                    raise ValueError("A2A completion not persisted")
                a2a_times.append((time.perf_counter() - before) * 1000)
            report["a2a_fixture_completed_and_readback"] = latency(a2a_times)
            report["api_rss_mb"] = None
            for line in Path(f"/proc/{api.pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    report["api_rss_mb"] = int(line.split()[1]) / 1024
            report["status"] = "PASS"
    except Exception as exc:
        report["errors"].append({"type": type(exc).__name__, "phase": "protocol_run"})
        raise
    finally:
        report["duration_seconds"] = time.perf_counter() - started
        for ws in sockets:
            with contextlib.suppress(Exception):
                await ws.close()
        api.terminate()
        try:
            api.wait(timeout=10)
        except subprocess.TimeoutExpired:
            api.kill()
            api.wait()
        await db.close()
        Path(output).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    asyncio.run(run(os.environ["HARNESS_OUTPUT"]))
