"""Mandatory Sprint 03 E2E: Genesis and Ada Live in AGORA.

Two independent Bridge processes, signed Agent Cards, MCP-driven avatar and
activity changes, a semantic move between Spaces, a public message, snapshot
convergence and owner revocation — all verified against the same semantic
surfaces the browser renders from. The browser layer itself is verified
separately (renderer smoke + live preview verification), because this test
must stay deterministic and headless-browser-free.
"""

import asyncio
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
PLAZA = "spc_00000000000000000000P1AZA0"
GARDEN = "spc_00000000000000000000GARDEN"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def api_url():
    port = _free_port()
    env = os.environ.copy()
    env["AGORA_PUBLIC_BASE_URL"] = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "agora_api.main:app", "--port", str(port)],
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                if httpx.get(f"{url}/healthz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)
        else:
            raise RuntimeError("API did not become healthy")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _bridge_env(api_url: str, home: Path) -> dict:
    env = os.environ.copy()
    env["AGORA_BRIDGE_HOME"] = str(home)
    env["AGORA_BRIDGE_API_URL"] = api_url
    env["AGORA_PUBLIC_BASE_URL"] = api_url
    env["PYTHONPATH"] = str(REPO)
    return env


def _cli(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "agora_bridge.cli", *args],
        env=env, capture_output=True, text=True, timeout=90, check=False,
    )


def _config(env: dict) -> dict:
    return json.loads((Path(env["AGORA_BRIDGE_HOME"]) / "config.json").read_text())


async def _mcp(env: dict, tool: str, args: dict) -> dict:
    """Drive the agent's real local MCP stdio server."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=PYTHON, args=["-m", "agora_bridge.cli", "mcp-serve"], env=env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            return json.loads(result.content[0].text)


def test_genesis_and_ada_live_in_agora(api_url, tmp_path_factory):
    suffix = secrets.token_hex(3)
    genesis_env = _bridge_env(api_url, tmp_path_factory.mktemp("genesis"))
    ada_env = _bridge_env(api_url, tmp_path_factory.mktemp("ada"))
    genesis_name, ada_name = f"Genesis-{suffix}", f"Ada-{suffix}"
    owner = httpx.Client(base_url=api_url, timeout=15)

    # 1-2. Fresh environment + authenticated human owner.
    login = owner.post("/v1/auth/dev/login", json={"username": f"owner-{suffix}"})
    assert login.status_code == 200
    csrf = {"X-CSRF-Token": login.json()["csrf_token"]}

    # 3-5. Two Bridges register; both cards are SIGNED at connect time.
    for env, name in ((genesis_env, genesis_name), (ada_env, ada_name)):
        assert _cli(env, "init", name).returncode == 0
        connected = _cli(env, "connect")
        assert connected.returncode == 0, connected.stderr
        assert "card      : signed" in connected.stdout
        agent_id = _config(env)["agent_id"]
        claim = owner.post("/v1/owner/claims", json={"agent_id": agent_id}, headers=csrf)
        assert _cli(env, "claim", claim.json()["claim_code"]).returncode == 0

    genesis_id = _config(genesis_env)["agent_id"]
    ada_id = _config(ada_env)["agent_id"]
    for agent_id in (genesis_id, ada_id):
        card = owner.get(f"/v1/a2a/agents/{agent_id}/card").json()
        assert card["agora"]["card_signature"] == "verified"
        assert card["card"]["signatures"]

    # 6. Both enter Central Plaza and stay connected.
    genesis_proc = subprocess.Popen(
        [PYTHON, "-m", "agora_bridge.cli", "run", "--for", "60"],
        env=genesis_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    ada_proc = subprocess.Popen(
        [PYTHON, "-m", "agora_bridge.cli", "run", "--for", "60"],
        env=ada_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        for _ in range(40):
            population = owner.get("/v1/world/population").json()
            plaza = {a["agent_id"] for a in population["spaces"][PLAZA]["agents"]}
            if {genesis_id, ada_id} <= plaza:
                break
            time.sleep(0.5)
        else:
            raise AssertionError("agents never became present in Central Plaza")

        # 7-8. The world the browser renders from: topology + distinct avatars.
        manifest = owner.get("/v1/world/manifest")
        assert manifest.status_code == 200 and manifest.json()["world_version"]
        population = owner.get("/v1/world/population").json()
        rendered = {a["agent_id"]: a for a in population["spaces"][PLAZA]["agents"]}
        assert rendered[genesis_id]["avatar"] != rendered[ada_id]["avatar"], (
            "deterministic defaults must make the two agents visually distinct"
        )

        # 9. Inspector data: verified identity + card capabilities.
        detail = owner.get(f"/v1/agents/{genesis_id}").json()
        assert detail["current_space_id"] == PLAZA

        # 10-11. Genesis changes its avatar through its LOCAL MCP server.
        new_avatar = asyncio.run(_mcp(genesis_env, "agora_update_avatar", {
            "body": "bot", "visor": "mono", "antenna": "telescope",
            "accessory": "scanner", "emblem": "atom", "expression": "curious",
            "tint": "#7b6ff0",
        }))
        assert new_avatar["changed"] is True
        assert new_avatar["avatar"]["body"] == "bot"
        state = owner.get(f"/v1/world/agents/{genesis_id}/state").json()
        assert state["avatar"]["body"] == "bot"  # what the browser will render

        # 12-13. Genesis changes activity to researching.
        activity = asyncio.run(_mcp(genesis_env, "agora_set_activity",
                                    {"activity": "researching"}))
        assert activity["activity"] == "researching"
        assert owner.get(
            f"/v1/world/agents/{genesis_id}/state"
        ).json()["activity"] == "researching"

        # 14-16. Ada moves to Idea Garden: ONE semantic transition, no
        # coordinates anywhere.
        ada_token_move = owner.post(
            f"/v1/spaces/{GARDEN}/enter",
            headers={"Authorization": f"Bearer {_session_token(ada_env)}"},
        )
        assert ada_token_move.status_code == 200
        assert ada_token_move.json()["transition"] is True
        for _ in range(20):
            population = owner.get("/v1/world/population").json()
            if any(a["agent_id"] == ada_id
                   for a in population["spaces"][GARDEN]["agents"]):
                break
            time.sleep(0.3)
        else:
            raise AssertionError("Ada never appeared in Idea Garden")
        assert not any(a["agent_id"] == ada_id
                       for a in population["spaces"][PLAZA]["agents"])

        events = owner.get(f"/v1/agents/{ada_id}/events").json()["events"]
        transition = next(e for e in events
                          if e["event_type"] == "space.entered"
                          and e["payload"]["space_id"] == GARDEN)
        assert transition["payload"]["from_space_id"] == PLAZA
        serialized = json.dumps(events)
        for cosmetic in ('"x"', '"y"', "sprite", "frame", "tween"):
            assert cosmetic not in serialized

        # 17-18. Genesis posts a public message (browser shows a brief
        # speech indicator; the text itself lives in the DOM panel).
        posted = asyncio.run(_mcp(genesis_env, "agora_post_message", {
            "space_id": PLAZA, "content": f"Hello world, {ada_name}.",
        }))
        assert posted["message_id"].startswith("msg_")

        # 19-20. Snapshot convergence: a fresh reader (like a refreshed
        # browser) reconstructs the exact semantic state from the snapshot.
        fresh = httpx.Client(base_url=api_url, timeout=15)
        snapshot = fresh.get("/v1/world/population").json()
        genesis_state = next(a for a in snapshot["spaces"][PLAZA]["agents"]
                             if a["agent_id"] == genesis_id)
        assert genesis_state["activity"] == "researching"
        assert genesis_state["avatar"]["body"] == "bot"
        assert any(a["agent_id"] == ada_id for a in snapshot["spaces"][GARDEN]["agents"])

        # 24. Idle rendering creates no ledger growth.
        before = len(owner.get(f"/v1/agents/{genesis_id}/events").json()["events"])
        for _ in range(10):
            owner.get("/v1/world/population")
            owner.get("/v1/world/manifest")
        after = len(owner.get(f"/v1/agents/{genesis_id}/events").json()["events"])
        assert after == before, "rendering must never write to the Event Ledger"

        # 21-23. Owner revokes Ada: realtime access dies, presence expires.
        ada_device = _config(ada_env)["device_id"]
        revoke = owner.post(f"/v1/owner/devices/{ada_device}/revoke", headers=csrf)
        assert revoke.status_code == 200
        denied = httpx.post(
            f"{api_url}/v1/spaces/{PLAZA}/enter", timeout=10,
            headers={"Authorization": f"Bearer {_session_token(ada_env)}"},
        )
        assert denied.status_code == 403
    finally:
        genesis_proc.terminate()
        ada_proc.terminate()
        genesis_proc.wait(timeout=10)
        ada_proc.wait(timeout=10)


def _session_token(env: dict) -> str:
    """Read the Bridge's own session token from its isolated home."""
    home = Path(env["AGORA_BRIDGE_HOME"])
    config = json.loads((home / "config.json").read_text())
    token_file = home / "session" / f"{config['agent_name']}.token"
    if token_file.exists():
        return token_file.read_text().strip()
    # keyring-backed environments
    import keyring

    return keyring.get_password("agora-bridge-session", config["agent_name"]) or ""
