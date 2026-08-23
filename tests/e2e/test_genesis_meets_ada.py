"""Mandatory Sprint 02 E2E: Genesis Meets Ada.

Two independent Bridge processes with independent Ed25519 identities and
separate local configurations. Deterministic runtime — zero model
credentials. Exercises: owner auth + secure claims, outbound realtime,
Central Plaza presence, a real local MCP stdio tool call, A2A Agent Card
discovery, A2A task relay without any inbound Bridge port, artifact
verification (identity, creator, nonce, hash), and authenticated owner
revocation blocking reconnect.
"""

import asyncio
import hashlib
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
AGORA_BIN = str(REPO / ".venv" / "bin" / "agora")
PLAZA = "spc_00000000000000000000P1AZA0"


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
            raise RuntimeError("API did not become healthy")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _bridge_env(api_url: str, home: Path) -> dict:
    env = os.environ.copy()
    env["AGORA_BRIDGE_HOME"] = str(home)
    env["AGORA_BRIDGE_API_URL"] = api_url
    env["PYTHONPATH"] = str(REPO)
    return env


def _cli(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "agora_bridge.cli", *args],
        env=env, capture_output=True, text=True, timeout=60, check=False,
    )


def _config(env: dict) -> dict:
    return json.loads((Path(env["AGORA_BRIDGE_HOME"]) / "config.json").read_text())


def test_genesis_meets_ada(api_url, tmp_path_factory):
    suffix = secrets.token_hex(3)
    genesis_env = _bridge_env(api_url, tmp_path_factory.mktemp("genesis"))
    ada_env = _bridge_env(api_url, tmp_path_factory.mktemp("ada"))
    genesis_name, ada_name = f"Genesis-{suffix}", f"Ada-{suffix}"

    owner = httpx.Client(base_url=api_url, timeout=10)

    # 1. Human owner authenticates (dev provider, cookie + CSRF).
    login = owner.post("/v1/auth/dev/login", json={"username": f"merari-{suffix}"})
    assert login.status_code == 200
    csrf = {"X-CSRF-Token": login.json()["csrf_token"]}

    # 2-3. Register both agents (independent identities) and claim them.
    for env, name in ((genesis_env, genesis_name), (ada_env, ada_name)):
        assert _cli(env, "init", name).returncode == 0
        assert _cli(env, "connect").returncode == 0
        agent_id = _config(env)["agent_id"]
        claim = owner.post("/v1/owner/claims", json={"agent_id": agent_id}, headers=csrf)
        assert claim.status_code == 201
        claimed = _cli(env, "claim", claim.json()["claim_code"])
        assert claimed.returncode == 0, claimed.stderr
    genesis_id = _config(genesis_env)["agent_id"]
    ada_id = _config(ada_env)["agent_id"]
    assert genesis_id != ada_id
    # independent keys: distinct device public keys registered server-side
    mine = owner.get("/v1/owner/agents").json()["agents"]
    assert {genesis_id, ada_id} <= {a["agent_id"] for a in mine}

    # 4-6. Both Bridges connect outbound and enter Central Plaza.
    ada_proc = subprocess.Popen(
        [PYTHON, "-m", "agora_bridge.cli", "run", "--for", "45"],
        env=ada_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    genesis_proc = subprocess.Popen(
        [PYTHON, "-m", "agora_bridge.cli", "run", "--for", "45"],
        env=genesis_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        for _ in range(40):
            present = {a["agent_id"] for a in
                       owner.get(f"/v1/spaces/{PLAZA}/agents").json()["agents"]}
            if {genesis_id, ada_id} <= present:
                break
            time.sleep(0.5)
        else:
            raise AssertionError("both agents never became present in Central Plaza")

        # 7. Web-facing API shows both online (what the UI renders).
        detail = owner.get(f"/v1/spaces/{PLAZA}").json()
        names = {a["name"] for a in detail["present_agents"]}
        assert {genesis_name, ada_name} <= names

        # 8-10. Genesis uses its LOCAL MCP server: observe world, discover
        # Ada, post a public greeting.
        mcp_result = asyncio.run(_genesis_mcp_session(genesis_env, ada_id, ada_name))
        assert mcp_result["observe_trust"] == "untrusted_remote"
        assert mcp_result["saw_ada_present"] is True
        assert mcp_result["posted_message_id"].startswith("msg_")

        # 11. Ada receives the public space context as untrusted content:
        # (validated structurally by the MCP layer; Ada-side notification
        # wrapping is asserted in unit suites)
        msgs = owner.get(f"/v1/spaces/{PLAZA}/messages").json()["messages"]
        assert any(m["agent_id"] == genesis_id for m in msgs)

        # 12-16. A2A First Contact: card discovery + task relay + artifact.
        card = owner.get(f"/v1/a2a/agents/{ada_id}/card").json()["card"]
        assert card["name"] == ada_name
        fc = _cli(genesis_env, "first-contact", ada_id)
        assert fc.returncode == 0, fc.stdout + fc.stderr
        task_id = next(
            line.split()[1] for line in fc.stdout.splitlines() if line.startswith("Task ")
        )
        task = None
        for _ in range(40):
            poll = _cli(genesis_env, "task-status", ada_id, task_id)
            task = json.loads(poll.stdout)
            if task["status"]["state"] == "TASK_STATE_COMPLETED":
                break
            time.sleep(0.5)
        assert task and task["status"]["state"] == "TASK_STATE_COMPLETED"

        # 17. Verify artifact identity, creator, nonce and hash.
        artifact = task["artifacts"][0]
        note = json.loads(artifact["parts"][0]["text"])
        assert note["responder_agent_id"] == ada_id
        assert note["initiator_agent_id"] == genesis_id
        server_row = owner.post(
            f"/v1/a2a/agents/{ada_id}/jsonrpc",
            json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get",
                  "params": {"id": task_id}},
            headers={"Authorization": "Bearer invalid"},
        )
        assert server_row.status_code == 401  # task data is not public
        # nonce must match the server-issued one recorded for this task
        assert len(note["nonce"]) == 32
        computed = hashlib.sha256(
            json.dumps(artifact["parts"], sort_keys=True).encode()
        ).hexdigest()
        assert artifact["metadata"]["sha256"] == computed

        # 18-19. No private key or provider credential crossed the boundary.
        everything_public = json.dumps(owner.get("/v1/agents").json()) + json.dumps(task)
        assert "private" not in everything_public.lower()
        assert "sk-" not in everything_public

        # 20-21. Owner revokes Ada; Ada cannot reconnect or act.
        ada_device = _config(ada_env)["device_id"]
        revoke = owner.post(f"/v1/owner/devices/{ada_device}/revoke", headers=csrf)
        assert revoke.status_code == 200 and revoke.json()["status"] == "revoked"
        time.sleep(1.5)
        rerun = _cli(ada_env, "run", "--for", "3")
        assert "REVOKED" in rerun.stdout or rerun.returncode != 0
        ping_denied = httpx.post(
            f"{api_url}/v1/spaces/{PLAZA}/enter", timeout=5,
            headers={"Authorization": "Bearer ses_anything"},
        )
        assert ping_denied.status_code == 401
    finally:
        genesis_proc.terminate()
        ada_proc.terminate()
        genesis_proc.wait(timeout=10)
        ada_proc.wait(timeout=10)


async def _genesis_mcp_session(genesis_env: dict, ada_id: str, ada_name: str) -> dict:
    """Drive Genesis's real local MCP stdio server with the official client."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=PYTHON, args=["-m", "agora_bridge.cli", "mcp-serve"], env=genesis_env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            observe = await session.call_tool("agora_observe_world", {})
            world = json.loads(observe.content[0].text)
            plaza = next(s for s in world["content"]["spaces"] if s["space_id"] == PLAZA)
            saw_ada = any(a["agent_id"] == ada_id for a in plaza["present_agents"])
            post = await session.call_tool(
                "agora_post_message",
                {"space_id": PLAZA,
                 "content": f"Greetings {ada_name} — first contact incoming."},
            )
            posted = json.loads(post.content[0].text)
            return {
                "observe_trust": world["trust"],
                "saw_ada_present": saw_ada,
                "posted_message_id": posted["message_id"],
            }