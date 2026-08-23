"""Sprint 02 realtime load harness (S2-T22).

Simulates N Bridge realtime connections (default 100) against a dedicated
API instance — no LLM inference anywhere. Measures connection establishment,
presence fanout, message latency, memory and ledger growth under heartbeats.

Run:  .venv/bin/python scripts/load_harness.py            (starts its own API)
"""

import asyncio
import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import websockets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[1]
PLAZA = "spc_00000000000000000000P1AZA0"
N_CONNECTIONS = int(os.environ.get("HARNESS_CONNECTIONS", "100"))
HEARTBEAT_ROUNDS = int(os.environ.get("HARNESS_HEARTBEAT_ROUNDS", "12"))


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def register(client: httpx.Client, name: str) -> dict:
    priv = Ed25519PrivateKey.generate()
    pub = b64url(priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    ch = client.post("/v1/registration/challenge",
                     json={"public_key": pub, "agent_name": name}).json()
    msg = f"agora.register.v1|{ch['challenge_id']}|{ch['nonce']}|{pub}|{name}".encode()
    sig = b64url(priv.sign(msg))
    return client.post("/v1/registration/register", json={
        "challenge_id": ch["challenge_id"], "public_key": pub, "agent_name": name,
        "signature": sig, "idempotency_key": f"harness-{secrets.token_hex(8)}"}).json()


def pctl(xs, p):
    return sorted(xs)[max(0, int(len(xs) * p) - 1)]


def rss_mb(pid: int) -> float:
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


async def bridge_session(url: str, token: str, results: dict, idx: int):
    t0 = time.perf_counter()
    ws = await websockets.connect(
        url, additional_headers={"Authorization": f"Bearer {token}"}, open_timeout=30
    )
    await ws.recv()  # welcome
    results["connect_ms"].append((time.perf_counter() - t0) * 1000)
    results["sockets"].append(ws)


async def main() -> None:
    port = free_port()
    env = os.environ.copy()
    env["AGORA_RATELIMIT_MAX_REQUESTS"] = "100000"
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "agora_api.main:app", "--port", str(port),
         "--log-level", "error"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    ws_url = f"ws://127.0.0.1:{port}/v1/realtime/bridge"
    client = httpx.Client(base_url=base, timeout=30)
    try:
        for _ in range(60):
            try:
                if client.get("/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)

        print(f"== AGORA load harness: {N_CONNECTIONS} simulated Bridges ==")
        regs = []
        t0 = time.perf_counter()
        for _ in range(N_CONNECTIONS):
            regs.append(register(client, f"Load-{secrets.token_hex(4)}"))
        print(f"registered {N_CONNECTIONS} agents in {time.perf_counter()-t0:.1f}s")

        client.get("/healthz")  # warm
        events_before = _count_events(client, regs[0])

        results = {"connect_ms": [], "sockets": []}
        t0 = time.perf_counter()
        await asyncio.gather(*(
            bridge_session(ws_url, r["session_token"], results, i)
            for i, r in enumerate(regs)
        ))
        total_connect = time.perf_counter() - t0
        cm = results["connect_ms"]
        print(f"{len(cm)} WS connections in {total_connect:.2f}s | "
              f"establishment p50 {pctl(cm,0.5):.1f} ms · p95 {pctl(cm,0.95):.1f} ms")

        # enter plaza + presence propagation latency (poll read-back)
        for r in regs[:20]:
            client.post(f"/v1/spaces/{PLAZA}/enter",
                        headers={"Authorization": f"Bearer {r['session_token']}"})
        t0 = time.perf_counter()
        while True:
            present = client.get(f"/v1/spaces/{PLAZA}/agents").json()["agents"]
            if len(present) >= 20 or time.perf_counter() - t0 > 10:
                break
        print(f"presence visible for 20 entrants after {(time.perf_counter()-t0)*1000:.0f} ms")

        # heartbeat rounds: ledger must not grow
        for _ in range(HEARTBEAT_ROUNDS):
            await asyncio.gather(*(
                ws.send(json.dumps({"type": "heartbeat"})) for ws in results["sockets"]
            ))
            await asyncio.sleep(0.2)
        events_after = _count_events(client, regs[0])
        hb_total = HEARTBEAT_ROUNDS * len(results["sockets"])
        print(f"{hb_total} heartbeats sent -> ledger event rows delta for probe agent: "
              f"{events_after - events_before} (expected 0 beyond explicit actions)")

        # message API latency
        msg_times = []
        token = regs[0]["session_token"]
        for i in range(50):
            t0 = time.perf_counter()
            client.post(f"/v1/spaces/{PLAZA}/messages",
                        json={"content": f"harness message {i}"},
                        headers={"Authorization": f"Bearer {token}"})
            msg_times.append((time.perf_counter() - t0) * 1000)
        print(f"space message POST p50 {pctl(msg_times,0.5):.1f} ms · "
              f"p95 {pctl(msg_times,0.95):.1f} ms")

        # a2a relay latency (offline target => submit only, no inference)
        a2a_times = []
        target = regs[1]
        for i in range(30):
            t0 = time.perf_counter()
            client.post(
                f"/v1/a2a/agents/{target['agent_id']}/jsonrpc",
                json={"jsonrpc": "2.0", "id": i, "method": "message/send",
                      "params": {"message": {
                          "messageId": f"m-{i}-{secrets.token_hex(4)}",
                          "role": "ROLE_USER", "parts": [{"text": "ping"}]}}},
                headers={"Authorization": f"Bearer {token}"})
            a2a_times.append((time.perf_counter() - t0) * 1000)
        print(f"a2a message/send p50 {pctl(a2a_times,0.5):.1f} ms · "
              f"p95 {pctl(a2a_times,0.95):.1f} ms")

        # footprints
        redis_info = subprocess.run(
            ["docker", "exec", "agora-dev-redis-1", "redis-cli", "info", "memory"],
            capture_output=True, text=True, check=False).stdout
        used = next((line.split(":")[1].strip() for line in redis_info.splitlines()
                     if line.startswith("used_memory_human")), "?")
        print(f"redis used_memory: {used}")
        print(f"api RSS with {len(results['sockets'])} live sockets: {rss_mb(api.pid):.0f} MB")

        for ws in results["sockets"]:
            await ws.close()
        print("== harness complete ==")
    finally:
        api.terminate()
        api.wait(timeout=10)


def _count_events(client: httpx.Client, reg: dict) -> int:
    events = client.get(f"/v1/agents/{reg['agent_id']}/events").json()["events"]
    return len(events)


if __name__ == "__main__":
    asyncio.run(main())
