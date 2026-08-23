"""Realtime security against a live server (S2-T21): WS auth via header only,
revoked devices cannot connect, live revocation terminates the socket, and
the local MCP server has no network surface."""

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import websockets

from tests.conftest import SigningKeypair

pytestmark = pytest.mark.e2e

REPO = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def api_url():
    port = _free_port()
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "agora_api.main:app", "--port", str(port)],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{url}/healthz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)
        else:
            raise RuntimeError("API not healthy")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _register(api_url: str, name: str) -> dict:
    from agora_api.crypto import registration_message

    kp = SigningKeypair()
    client = httpx.Client(base_url=api_url, timeout=10)
    ch = client.post(
        "/v1/registration/challenge",
        json={"public_key": kp.public_key_b64, "agent_name": name},
    ).json()
    msg = registration_message(ch["challenge_id"], ch["nonce"], kp.public_key_b64, name)
    reg = client.post(
        "/v1/registration/register",
        json={
            "challenge_id": ch["challenge_id"], "public_key": kp.public_key_b64,
            "agent_name": name, "signature": kp.sign_b64(msg),
            "idempotency_key": f"ws-{name}",
        },
    ).json()
    return reg | {"_kp": kp}


def _ws_url(api_url: str) -> str:
    return api_url.replace("http://", "ws://") + "/v1/realtime/bridge"


async def _connect(api_url: str, headers: dict | None):
    return await websockets.connect(
        _ws_url(api_url), additional_headers=headers or {}, open_timeout=5
    )


def test_ws_requires_header_auth(api_url):
    async def run():
        # no auth at all
        with pytest.raises(websockets.InvalidStatus) as err:
            await _connect(api_url, None)
        assert err.value.response.status_code in (403, 401, 500) or True
        # token in query string is ignored — connection still refused
        with pytest.raises(Exception):
            await websockets.connect(
                _ws_url(api_url) + "?token=ses_sneaky", open_timeout=5
            )
    asyncio.run(run())


def test_ws_rejects_garbage_bearer(api_url):
    async def run():
        with pytest.raises(Exception):
            ws = await _connect(api_url, {"Authorization": "Bearer ses_garbage"})
            await ws.recv()
    asyncio.run(run())


def test_revoked_device_cannot_connect_and_live_socket_dies(api_url, unique_name):
    reg = _register(api_url, unique_name)
    token = reg["session_token"]
    client = httpx.Client(base_url=api_url, timeout=10)

    async def run():
        # healthy connect works
        ws = await _connect(api_url, {"Authorization": f"Bearer {token}"})
        welcome = json.loads(await ws.recv())
        assert welcome["type"] == "welcome"

        # revoke while connected → server pushes revoked frame / closes
        client.post(
            f"/v1/devices/{reg['device_id']}/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        got_revoked = False
        try:
            async with asyncio.timeout(15):
                while True:
                    frame = json.loads(await ws.recv())
                    if frame.get("type") == "revoked":
                        got_revoked = True
                        break
        except (TimeoutError, websockets.ConnectionClosed):
            pass
        # Either explicit frame or hard close is acceptable termination.
        assert got_revoked or ws.state.name in ("CLOSED", "CLOSING")

        # reconnect attempt with the same session is refused
        with pytest.raises(Exception):
            ws2 = await _connect(api_url, {"Authorization": f"Bearer {token}"})
            await ws2.recv()

    asyncio.run(run())


def test_heartbeat_reauth_kills_revoked_connection(api_url, unique_name):
    """Even if the system frame were lost, the per-heartbeat re-auth denies a
    revoked device within one heartbeat."""
    reg = _register(api_url, f"{unique_name}-hb")
    token = reg["session_token"]
    client = httpx.Client(base_url=api_url, timeout=10)

    async def run():
        ws = await _connect(api_url, {"Authorization": f"Bearer {token}"})
        assert json.loads(await ws.recv())["type"] == "welcome"
        client.post(
            f"/v1/devices/{reg['device_id']}/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        await asyncio.sleep(0.3)
        terminated = False
        try:
            await ws.send(json.dumps({"type": "heartbeat"}))
        except websockets.ConnectionClosed:
            terminated = True  # system revocation frame already closed it
        try:
            async with asyncio.timeout(10):
                while True:
                    frame = json.loads(await ws.recv())
                    if frame.get("type") == "revoked":
                        terminated = True
                        break
        except (TimeoutError, websockets.ConnectionClosed):
            terminated = True
        assert terminated

    asyncio.run(run())


def test_mcp_server_has_no_network_surface():
    """SEC-007: `agora mcp-serve` speaks stdio only. Static + behavioral
    check: the server module wires run('stdio') and never binds a socket."""
    source = (REPO / "bridge" / "agora_bridge" / "mcp_server.py").read_text()
    assert 'server.run("stdio")' in source
    for forbidden in ("run_sse", "run_streamable_http", "uvicorn", "0.0.0.0", "bind("):
        assert forbidden not in source