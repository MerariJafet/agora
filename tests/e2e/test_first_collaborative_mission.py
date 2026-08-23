"""Mandatory Sprint 05 E2E: The First Collaborative Mission.

Genesis (coordinator), Ada (researcher) and Turing (reviewer) run a real
Mission end to end through the actual local MCP server, exactly as an
attached runtime would: a dependent two-task DAG, a leased claim, an
immutable published ArtifactVersion, a needs_changes -> revision -> approve
review cycle, a completion evaluator that pins the exact final
ArtifactVersion ids, and a second Mission that reuses one of those versions
as an explicitly pinned input — proving the pin survives even after a
later v3 of the same Artifact exists.
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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def api_url():
    import time

    port = _free_port()
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "agora_api.main:app", "--port", str(port)],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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
    env["PYTHONPATH"] = str(REPO)
    return env


def _cli(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "agora_bridge.cli", *args],
        env=env, capture_output=True, text=True, timeout=60, check=False,
    )


def _config(env: dict) -> dict:
    return json.loads((Path(env["AGORA_BRIDGE_HOME"]) / "config.json").read_text())


async def _mcp(env: dict, tool: str, args: dict) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=PYTHON, args=["-m", "agora_bridge.cli", "mcp-serve"], env=env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            payload = json.loads(result.content[0].text)
            if result.is_error:
                raise AssertionError(f"{tool} failed: {payload}")
            return payload


def test_first_collaborative_mission(api_url, tmp_path_factory):
    suffix = secrets.token_hex(3)
    genesis_env = _bridge_env(api_url, tmp_path_factory.mktemp("genesis"))
    ada_env = _bridge_env(api_url, tmp_path_factory.mktemp("ada"))
    turing_env = _bridge_env(api_url, tmp_path_factory.mktemp("turing"))
    genesis_name, ada_name, turing_name = (
        f"Genesis-{suffix}", f"Ada-{suffix}", f"Turing-{suffix}"
    )
    owner = httpx.Client(base_url=api_url, timeout=15)

    # 1. Fresh, independent Bridges for all three agents.
    for env, name in ((genesis_env, genesis_name), (ada_env, ada_name), (turing_env, turing_name)):
        assert _cli(env, "init", name).returncode == 0
        connected = _cli(env, "connect")
        assert connected.returncode == 0, connected.stderr
    genesis_id = _config(genesis_env)["agent_id"]
    ada_id = _config(ada_env)["agent_id"]
    turing_id = _config(turing_env)["agent_id"]

    # Ada is the only agent that ever publishes local bytes; grant only her
    # Bridge files.read (never automatic, always an explicit owner action).
    assert _cli(ada_env, "grant", "files.read").returncode == 0

    workdir = tmp_path_factory.mktemp("ada-workspace")
    arguments_file = workdir / "arguments.md"
    arguments_file.write_text("# Extracted arguments\n- Point A\n- Point B\n")
    policy_v1_file = workdir / "policy.md"
    policy_v1_file.write_text("# Policy draft v1\nNo citations yet.\n")
    policy_v2_file = workdir / "policy_v2.md"
    policy_v2_file.write_text("# Policy draft v2\nNow with citations [1][2].\n")
    policy_v3_file = workdir / "policy_v3.md"
    policy_v3_file.write_text("# Policy draft v3 (later, unrelated Mission)\n")

    # 2. Genesis creates and activates a Mission with an explicit, frozen
    # completion policy (no Arena Points, no ranking — just structure).
    mission = asyncio.run(_mcp(genesis_env, "agora_create_mission", {
        "title": "Draft a sourcing policy",
        "objective": "Extract arguments, then draft and land a reviewed policy.",
        "max_participants": 5,
    }))
    mission_id = mission["mission_id"]
    activated = httpx.post(
        f"{api_url}/v1/missions/{mission_id}/activate",
        headers={"Authorization": f"Bearer {_token(genesis_env, genesis_name)}"}, timeout=10,
    )
    assert activated.status_code == 200
    assert activated.json()["state"] == "active"

    # 3. Ada (researcher) and Turing (reviewer) join with explicit roles.
    asyncio.run(_mcp(ada_env, "agora_join_mission", {"mission_id": mission_id, "roles": ["researcher"]}))
    asyncio.run(_mcp(turing_env, "agora_join_mission", {"mission_id": mission_id, "roles": ["reviewer"]}))
    detail = owner.get(f"/v1/missions/{mission_id}").json()
    assert {ada_id, turing_id} <= {p["agent_id"] for p in detail["participants"]}

    # 4. Genesis defines a dependent two-task DAG: Task B needs Task A done.
    genesis_token = _token(genesis_env, genesis_name)
    task_a = httpx.post(
        f"{api_url}/v1/missions/{mission_id}/tasks",
        json={"title": "Extract arguments", "description": "Pull out the core arguments."},
        headers={"Authorization": f"Bearer {genesis_token}"}, timeout=10,
    ).json()
    task_b = httpx.post(
        f"{api_url}/v1/missions/{mission_id}/tasks",
        json={"title": "Draft policy", "description": "Draft a policy from the arguments.",
              "dependency_task_ids": [task_a["mission_task_id"]]},
        headers={"Authorization": f"Bearer {genesis_token}"}, timeout=10,
    ).json()
    assert task_a["state"] == "ready"
    assert task_b["state"] == "pending"  # blocked on Task A until it is accepted

    # 5. Task A is worked through REAL cross-Bridge A2A delegation (S5.1-T04),
    # not Ada polling/claiming on her own initiative: Genesis pushes the work
    # over the existing outbound-only A2A relay to Ada's connected Bridge,
    # whose MissionAwareRuntime publishes the Artifact and submits the
    # MissionTask through the same, already-accepted Mission API a manual
    # MCP call would use — the delegation only changes HOW the work order
    # arrives, never the MissionTask/Artifact source-of-truth mechanisms.
    arguments_artifact = asyncio.run(_mcp(ada_env, "agora_create_artifact", {
        "title": "Extracted Arguments", "artifact_type": "analysis",
    }))
    handlers_file = workdir / "ada_mission_handlers.json"
    handlers_file.write_text(json.dumps({
        task_a["mission_task_id"]: {
            "artifact_id": arguments_artifact["artifact_id"],
            "file_path": str(arguments_file), "media_type": "text/markdown",
        }
    }))
    ada_runtime_proc = subprocess.Popen(
        [PYTHON, "-m", "agora_bridge.cli", "run", "--for", "30",
         "--mission-handlers", str(handlers_file)],
        env=ada_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        # Ada's Bridge must actually be connected before delegation, or the
        # A2A relay would (correctly) queue the task for her next connect
        # instead of delivering it live.
        PLAZA = "spc_00000000000000000000P1AZA0"
        for _ in range(40):
            present = {
                a["agent_id"]
                for a in httpx.get(f"{api_url}/v1/spaces/{PLAZA}/agents", timeout=5).json()["agents"]
            }
            if ada_id in present:
                break
            time.sleep(0.25)
        else:
            raise AssertionError("Ada's Bridge never entered the Space before delegation")

        delegated = httpx.post(
            f"{api_url}/v1/mission-tasks/{task_a['mission_task_id']}/delegate",
            json={"target_agent_id": ada_id},
            headers={"Authorization": f"Bearer {genesis_token}"}, timeout=10,
        )
        assert delegated.status_code == 200, delegated.text
        a2a_task_id = delegated.json()["a2a_task_id"]

        for _ in range(60):
            task_a_now = httpx.get(f"{api_url}/v1/mission-tasks/{task_a['mission_task_id']}").json()
            if task_a_now["state"] == "submitted":
                break
            time.sleep(0.5)
        else:
            raise AssertionError(
                f"Task A never reached 'submitted' via A2A delegation; last seen: {task_a_now}"
            )
        arguments_version_id = task_a_now["result_artifact_version_id"]
        assert arguments_version_id, "Ada's MissionAwareRuntime must have pinned a real version"

        delegation_status = httpx.get(
            f"{api_url}/v1/mission-tasks/{task_a['mission_task_id']}/delegation", timeout=10
        ).json()
        assert delegation_status["a2a_task_id"] == a2a_task_id
        assert delegation_status["a2a_status"] == "completed"
    finally:
        ada_runtime_proc.terminate()
        ada_runtime_proc.wait(timeout=10)

    arguments_version = httpx.get(
        f"{api_url}/v1/artifact-versions/{arguments_version_id}", timeout=10
    ).json()
    assert arguments_version["version_number"] == 1
    assert arguments_version["provenance_manifest"]["mission_id"] == mission_id
    assert arguments_version["provenance_manifest"]["mission_task_ids"] == [
        task_a["mission_task_id"]
    ]

    # 6. Genesis accepts Task A -> Task B becomes ready.
    accepted_a = httpx.post(
        f"{api_url}/v1/mission-tasks/{task_a['mission_task_id']}/accept",
        headers={"Authorization": f"Bearer {genesis_token}"}, timeout=10,
    )
    assert accepted_a.status_code == 200
    task_b_refreshed = asyncio.run(_mcp(ada_env, "agora_get_mission_task", {"task_id": task_b["mission_task_id"]}))
    assert task_b_refreshed["content"]["state"] == "ready"

    # 7. Ada claims Task B, publishes Policy Draft v1 declaring Task A's
    # exact ArtifactVersion as a source (pinned, never "latest").
    asyncio.run(_mcp(ada_env, "agora_claim_mission_task", {"task_id": task_b["mission_task_id"]}))
    policy_artifact = asyncio.run(_mcp(ada_env, "agora_create_artifact", {
        "title": "Sourcing Policy", "artifact_type": "report",
    }))
    policy_v1 = asyncio.run(_mcp(ada_env, "agora_publish_artifact", {
        "artifact_id": policy_artifact["artifact_id"], "file_path": str(policy_v1_file),
        "media_type": "text/markdown", "mission_id": mission_id,
        "mission_task_id": task_b["mission_task_id"],
    }))
    asyncio.run(_mcp(ada_env, "agora_submit_mission_task", {
        "task_id": task_b["mission_task_id"], "artifact_version_id": policy_v1["artifact_version_id"],
    }))

    # 8. Turing reviews v1 and requests changes; the loop is explicit, not
    # an in-place edit — v1 remains forever exactly what was reviewed.
    review1 = asyncio.run(_mcp(turing_env, "agora_review_artifact", {
        "artifact_version_id": policy_v1["artifact_version_id"],
        "verdict": "needs_changes", "comment": "Add citations before this can land.",
    }))
    assert review1["verdict"] == "needs_changes"
    genesis_env_token_header = {"Authorization": f"Bearer {genesis_token}"}
    revision = httpx.post(
        f"{api_url}/v1/mission-tasks/{task_b['mission_task_id']}/request-revision",
        headers=genesis_env_token_header, timeout=10,
    )
    assert revision.status_code == 200
    assert revision.json()["state"] == "needs_revision"

    # 9. Ada re-claims Task B, publishes v2 (parented to v1), Turing approves.
    asyncio.run(_mcp(ada_env, "agora_claim_mission_task", {"task_id": task_b["mission_task_id"]}))
    policy_v2 = asyncio.run(_mcp(ada_env, "agora_publish_artifact", {
        "artifact_id": policy_artifact["artifact_id"], "file_path": str(policy_v2_file),
        "media_type": "text/markdown", "mission_id": mission_id,
        "mission_task_id": task_b["mission_task_id"],
        "parent_artifact_version_id": policy_v1["artifact_version_id"],
    }))
    assert policy_v2["version_number"] == 2
    assert policy_v2["provenance_manifest"]["parent_artifact_version_ids"] == [
        policy_v1["artifact_version_id"]
    ]
    asyncio.run(_mcp(ada_env, "agora_submit_mission_task", {
        "task_id": task_b["mission_task_id"], "artifact_version_id": policy_v2["artifact_version_id"],
    }))
    review2 = asyncio.run(_mcp(turing_env, "agora_review_artifact", {
        "artifact_version_id": policy_v2["artifact_version_id"], "verdict": "approve",
    }))
    assert review2["verdict"] == "approve"
    assert review2["is_self_review"] is False

    # 10. Genesis accepts Task B: completion policy evaluates, and the
    # Mission completes pinning the EXACT final ArtifactVersion ids
    # (Task A's v1 and Task B's v2 — never v1 of the policy, never "latest").
    accepted_b = httpx.post(
        f"{api_url}/v1/mission-tasks/{task_b['mission_task_id']}/accept",
        headers=genesis_env_token_header, timeout=10,
    )
    assert accepted_b.status_code == 200
    final_mission = owner.get(f"/v1/missions/{mission_id}").json()
    assert final_mission["state"] == "completed"
    assert sorted(final_mission["final_artifact_version_ids"]) == sorted(
        [arguments_version["artifact_version_id"], policy_v2["artifact_version_id"]]
    )

    # 11. A second, independent Mission reuses the approved Policy v2 as an
    # explicitly pinned input. Publishing a LATER v3 of the same Artifact
    # afterward must NOT change what the second Mission's manifest recorded.
    mission_2 = asyncio.run(_mcp(genesis_env, "agora_create_mission", {
        "title": "Apply the sourcing policy",
        "objective": "Use the approved policy to write an application note.",
    }))
    mission_2_id = mission_2["mission_id"]
    httpx.post(
        f"{api_url}/v1/missions/{mission_2_id}/activate",
        headers=genesis_env_token_header, timeout=10,
    )
    asyncio.run(_mcp(ada_env, "agora_join_mission", {"mission_id": mission_2_id, "roles": ["researcher"]}))
    task_c = httpx.post(
        f"{api_url}/v1/missions/{mission_2_id}/tasks",
        json={"title": "Apply policy", "description": "Write the application note."},
        headers=genesis_env_token_header, timeout=10,
    ).json()
    asyncio.run(_mcp(ada_env, "agora_claim_mission_task", {"task_id": task_c["mission_task_id"]}))

    application_artifact = asyncio.run(_mcp(ada_env, "agora_create_artifact", {
        "title": "Policy Application Note", "artifact_type": "document",
    }))
    application_version = asyncio.run(_mcp(ada_env, "agora_publish_artifact", {
        "artifact_id": application_artifact["artifact_id"], "file_path": str(policy_v1_file),
        "media_type": "text/markdown", "mission_id": mission_2_id,
        "mission_task_id": task_c["mission_task_id"],
        "parent_artifact_version_id": policy_v2["artifact_version_id"],
    }))
    assert application_version["provenance_manifest"]["parent_artifact_version_ids"] == [
        policy_v2["artifact_version_id"]
    ]

    # Now publish a hypothetical v3 of the Policy artifact.
    policy_v3 = asyncio.run(_mcp(ada_env, "agora_publish_artifact", {
        "artifact_id": policy_artifact["artifact_id"], "file_path": str(policy_v3_file),
        "media_type": "text/markdown",
    }))
    assert policy_v3["version_number"] == 3

    # The second Mission's already-published version is immutable: its
    # provenance manifest still names v2, not v3 and not "latest".
    refetched = owner.get(f"/v1/artifact-versions/{application_version['artifact_version_id']}").json()
    assert refetched["provenance_manifest"]["parent_artifact_version_ids"] == [
        policy_v2["artifact_version_id"]
    ]
    assert policy_v3["artifact_version_id"] not in refetched["provenance_manifest"][
        "parent_artifact_version_ids"
    ]

    # 12. Never any competitive/ranking language anywhere in the flow.
    for forbidden in ("arena_points", "elo", "winner", "ranking", "leaderboard"):
        assert forbidden not in json.dumps(final_mission).lower()


def _token(env: dict, name: str) -> str:
    token_file = Path(env["AGORA_BRIDGE_HOME"]) / "session" / f"{name}.token"
    if token_file.exists():
        return token_file.read_text().strip()
    import keyring

    token = keyring.get_password("agora-bridge-session", name)
    assert token, f"no session token found for {name}"
    return token
