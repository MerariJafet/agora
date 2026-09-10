"""Mission/Artifact realtime fanout is scoped by interest (S5.1-T06):
a browser must explicitly subscribe to a Mission id (same WS subscribe
mechanism already used for Spaces) to receive its semantic events, lease
renewal never generates a frame, and nothing is broadcast unscoped."""

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
        "/v1/registration/challenge", json={"public_key": kp.public_key_b64, "agent_name": name}
    ).json()
    msg = registration_message(ch["challenge_id"], ch["nonce"], kp.public_key_b64, name)
    reg = client.post(
        "/v1/registration/register",
        json={"challenge_id": ch["challenge_id"], "public_key": kp.public_key_b64,
              "agent_name": name, "signature": kp.sign_b64(msg),
              "idempotency_key": f"rt-{name}"},
    ).json()
    return reg


def test_mission_events_are_scoped_not_broadcast(api_url):
    import secrets

    genesis = _register(api_url, "GenesisRT")
    auth = {"Authorization": f"Bearer {genesis['session_token']}"}
    client = httpx.Client(base_url=api_url, timeout=10)

    mission = client.post(
        "/v1/missions", json={"title": "Realtime check", "objective": "..."}, headers=auth
    ).json()
    mission_id = mission["mission_id"]

    # Browser-side realtime requires an owner cookie session (same auth as
    # every other browser-originated realtime/mutation surface).
    login = httpx.Client(base_url=api_url, timeout=10)
    login.post("/v1/auth/dev/login", json={"username": f"owner-{secrets.token_hex(4)}"})
    cookie_header = "; ".join(f"{k}={v}" for k, v in login.cookies.items())

    async def _scenario():
        ws_url = api_url.replace("http://", "ws://") + "/v1/realtime/web"
        headers = {"Cookie": cookie_header}
        async with websockets.connect(ws_url, additional_headers=headers) as subscribed, \
                websockets.connect(ws_url, additional_headers=headers) as unsubscribed:
            await subscribed.send(json.dumps({"type": "subscribe", "space_id": mission_id}))
            ack = json.loads(await asyncio.wait_for(subscribed.recv(), timeout=5))
            assert ack == {"type": "subscribed", "space_id": mission_id}, ack

            task = client.post(
                f"/v1/missions/{mission_id}/tasks",
                json={"title": "T", "description": "..."}, headers=auth,
            ).json()

            frame = json.loads(await asyncio.wait_for(subscribed.recv(), timeout=5))
            assert frame["type"] == "mission"
            assert frame["event"] == "task_created"
            assert frame["mission_task_id"] == task["mission_task_id"]

            # The unsubscribed client (interested in nothing) must receive
            # nothing at all — there is no unscoped "global" broadcast.
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(unsubscribed.recv(), timeout=1)

            # Claiming the task fans out too...
            client.post(f"/v1/mission-tasks/{task['mission_task_id']}/claim", headers=auth)
            claimed = json.loads(await asyncio.wait_for(subscribed.recv(), timeout=5))
            assert claimed["event"] == "task_claimed"

            # ...but renewing the lease is not a semantic change and must
            # produce NO frame at all.
            client.post(f"/v1/mission-tasks/{task['mission_task_id']}/renew-lease", headers=auth)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(subscribed.recv(), timeout=1)

    asyncio.run(_scenario())
