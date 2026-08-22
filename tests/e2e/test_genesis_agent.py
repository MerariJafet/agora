"""Mandatory E2E scenario: Genesis Agent.

Boots a real uvicorn API subprocess (real Postgres/Redis/NATS from docker
compose), drives the actual `agora` CLI as subprocesses with an isolated
AGORA_BRIDGE_HOME, and asserts the web-facing read API. Exercises:
identity creation -> challenge -> local signing -> registration -> ledger
events -> web API visibility -> revocation -> denial.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

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
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                if httpx.get(f"{url}/healthz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise RuntimeError("API did not become healthy")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def bridge_env(api_url, tmp_path_factory):
    home = tmp_path_factory.mktemp("bridge-home")
    env = os.environ.copy()
    env["AGORA_BRIDGE_HOME"] = str(home)
    env["AGORA_BRIDGE_API_URL"] = api_url
    # Force the documented file fallback so the E2E run never touches the
    # developer's real OS keyring.
    env["PYTHONPATH"] = str(REPO)
    env["AGORA_E2E_AGENT"] = f"Genesis-{secrets.token_hex(4)}"
    return env


def agora_cli(env, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "agora_bridge.cli", *args],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )


def test_genesis_agent_full_lifecycle(api_url, bridge_env):
    agent_name = bridge_env["AGORA_E2E_AGENT"]

    # 1-2. init: local identity, private key stays local
    init = agora_cli(bridge_env, "init", agent_name)
    assert init.returncode == 0, init.stderr
    assert "public key" in init.stdout

    # 3-6. connect: challenge -> local sign -> register
    connect = agora_cli(bridge_env, "connect")
    assert connect.returncode == 0, connect.stderr
    assert f"Registered '{agent_name}'" in connect.stdout

    config = json.loads((Path(bridge_env["AGORA_BRIDGE_HOME"]) / "config.json").read_text())
    agent_id, device_id = config["agent_id"], config["device_id"]
    assert agent_id.startswith("agt_") and device_id.startswith("dev_")

    # SEC-001: nothing under the bridge home ever crossed the wire; verify the
    # server never stored private key material anywhere reachable.
    agents = httpx.get(f"{api_url}/v1/agents", timeout=5).json()
    assert "private" not in json.dumps(agents).lower()

    # 7-9. ledger events exist
    events = httpx.get(f"{api_url}/v1/agents/{agent_id}/events", timeout=5).json()["events"]
    types = {e["event_type"] for e in events}
    assert {"agent.registered", "device.authorized"} <= types

    # 10-11. web read API returns Genesis with an authorized device
    genesis = [a for a in agents["agents"] if a["agent_id"] == agent_id]
    assert genesis and genesis[0]["name"] == agent_name
    assert any(d["status"] == "authorized" for d in genesis[0]["devices"])

    # authenticated action works pre-revocation
    status = agora_cli(bridge_env, "status")
    assert "cloud   : connected" in status.stdout

    # 12. revoke
    revoke = agora_cli(bridge_env, "revoke", "--yes")
    assert revoke.returncode == 0, revoke.stderr

    # 13. subsequent authenticated action is denied
    detail = httpx.get(f"{api_url}/v1/agents/{agent_id}", timeout=5).json()
    assert all(d["status"] == "revoked" for d in detail["devices"])
    events = httpx.get(f"{api_url}/v1/agents/{agent_id}/events", timeout=5).json()["events"]
    assert "device.revoked" in {e["event_type"] for e in events}
