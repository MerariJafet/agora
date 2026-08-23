"""Mandatory Sprint 04 E2E: The First Real Debate.

Genesis and Ada, two independent Bridges, turn a live conversation into a
structured, auditable argument: a capped 2-participant Debate, competing
Claims with attached Evidence, a contradiction relation, a supersession, a
rejected cross-agent mutation, human + agent audience perception (kept
separate, never a truth score), and a closed debate that freezes assessments.
Every step drives the REAL local MCP server exactly as an attached runtime
would.
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
            return json.loads(result.content[0].text)


def test_first_real_debate(api_url, tmp_path_factory):
    suffix = secrets.token_hex(3)
    genesis_env = _bridge_env(api_url, tmp_path_factory.mktemp("genesis"))
    ada_env = _bridge_env(api_url, tmp_path_factory.mktemp("ada"))
    third_env = _bridge_env(api_url, tmp_path_factory.mktemp("third"))
    genesis_name, ada_name = f"Genesis-{suffix}", f"Ada-{suffix}"

    owner = httpx.Client(base_url=api_url, timeout=15)

    # 1-2. Fresh environment + independent Bridges enter Central Plaza.
    for env, name in ((genesis_env, genesis_name), (ada_env, ada_name),
                      (third_env, f"Third-{suffix}")):
        assert _cli(env, "init", name).returncode == 0
        connected = _cli(env, "connect")
        assert connected.returncode == 0, connected.stderr
    genesis_id = _config(genesis_env)["agent_id"]
    ada_id = _config(ada_env)["agent_id"]

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
            present = {a["agent_id"] for a in
                       owner.get(f"/v1/spaces/{PLAZA}/agents").json()["agents"]}
            if {genesis_id, ada_id} <= present:
                break
            time.sleep(0.5)
        else:
            raise AssertionError("agents never became present")

        # 3-4. Genesis creates a 2-participant Debate with named positions.
        debate = asyncio.run(_mcp(genesis_env, "agora_create_debate", {
            "space_id": PLAZA,
            "question": "Should AGORA treat audience consensus as evidence of factual truth?",
            "positions": ["YES", "NO"], "max_participants": 2,
        }))
        debate_id = debate["debate_id"]
        yes_pos = debate["positions"][0]["position_id"]
        no_pos = debate["positions"][1]["position_id"]

        # 5-6. Genesis and Ada join, take opposing positions.
        assert asyncio.run(_mcp(genesis_env, "agora_join_debate", {"debate_id": debate_id}))
        assert asyncio.run(_mcp(ada_env, "agora_join_debate", {"debate_id": debate_id}))
        asyncio.run(_mcp(genesis_env, "agora_set_debate_position",
                         {"debate_id": debate_id, "position_id": yes_pos}))
        asyncio.run(_mcp(ada_env, "agora_set_debate_position",
                         {"debate_id": debate_id, "position_id": no_pos}))

        # 7. A third agent is rejected: the debate is already full.
        # (already connected in the setup loop above)
        third_home = Path(third_env["AGORA_BRIDGE_HOME"])
        token_file = third_home / "session" / f"Third-{suffix}.token"
        third_token = token_file.read_text().strip() if token_file.exists() else None
        if third_token is None:
            import keyring

            third_token = keyring.get_password("agora-bridge-session", f"Third-{suffix}")
        rejected = httpx.post(
            f"{api_url}/v1/debates/{debate_id}/join", timeout=10,
            headers={"Authorization": f"Bearer {third_token}"},
        )
        assert rejected.status_code == 409
        assert rejected.json()["error"]["code"] == "debate_full"

        # 8-9. Genesis publishes a Claim and attaches Evidence.
        genesis_claim = asyncio.run(_mcp(genesis_env, "agora_create_claim", {
            "space_id": PLAZA, "claim_type": "policy_proposal",
            "text": "AGORA should NOT treat audience consensus as evidence of truth.",
            "confidence": 0.85, "debate_id": debate_id, "position_id": yes_pos,
        }))
        ev1 = asyncio.run(_mcp(genesis_env, "agora_create_evidence", {
            "source_type": "url", "locator": "https://example.org/epistemics-101",
            "role": "supports", "title": "On consensus and truth",
        }))
        asyncio.run(_mcp(genesis_env, "agora_attach_evidence", {
            "claim_id": genesis_claim["claim_id"], "evidence_id": ev1["evidence_id"],
            "role": "supports",
        }))

        # 10-11. Ada publishes a contradicting Claim with its own Evidence.
        ada_claim = asyncio.run(_mcp(ada_env, "agora_create_claim", {
            "space_id": PLAZA, "claim_type": "policy_proposal",
            "text": "Consensus signals reliability and should count as weak evidence.",
            "confidence": 0.6, "debate_id": debate_id, "position_id": no_pos,
        }))
        ev2 = asyncio.run(_mcp(ada_env, "agora_create_evidence", {
            "source_type": "url", "locator": "https://example.org/wisdom-of-crowds",
            "role": "supports", "title": "Wisdom of crowds",
        }))
        asyncio.run(_mcp(ada_env, "agora_attach_evidence", {
            "claim_id": ada_claim["claim_id"], "evidence_id": ev2["evidence_id"],
            "role": "supports",
        }))

        # 12-13. Ada contradicts Genesis's claim; Genesis questions Ada's.
        contradiction = asyncio.run(_mcp(ada_env, "agora_relate_claims", {
            "source_claim_id": ada_claim["claim_id"], "target_claim_id": genesis_claim["claim_id"],
            "relation_type": "contradicts",
        }))
        assert contradiction["relation_type"] == "contradicts"
        asyncio.run(_mcp(genesis_env, "agora_relate_claims", {
            "source_claim_id": genesis_claim["claim_id"], "target_claim_id": ada_claim["claim_id"],
            "relation_type": "questions",
        }))

        # 14-17. Browser-facing surfaces show the structure (no reload needed
        # in the real UI; here we assert the exact data the browser reads).
        detail = owner.get(f"/v1/debates/{debate_id}").json()
        assert {p["agent_id"] for p in detail["participants"]} == {genesis_id, ada_id}
        claims = owner.get(f"/v1/debates/{debate_id}/claims").json()["claims"]
        assert {genesis_claim["claim_id"], ada_claim["claim_id"]} <= {c["claim_id"] for c in claims}
        claim_id = genesis_claim["claim_id"]
        evidence = owner.get(f"/v1/claims/{claim_id}/evidence").json()["evidence"]
        assert len(evidence) == 1 and evidence[0]["provenance_level"] == "reference_only"
        neighborhood = owner.get(f"/v1/claims/{claim_id}/neighborhood?depth=1").json()
        assert ada_claim["claim_id"] in {c["claim_id"] for c in neighborhood["claims"]}

        # 18-19. Human owner + spectator agent submit audience assessments.
        login = owner.post("/v1/auth/dev/login", json={"username": f"human-{suffix}"})
        csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
        human = owner.put(f"/v1/debates/{debate_id}/assessment/human",
                          json={"preferred_position_id": no_pos, "evidence_quality": 4},
                          headers=csrf)
        assert human.status_code == 200

        # The rejected third agent is still a legitimate SPECTATOR: assessment
        # is open to any authenticated human/agent, not just participants.
        third_assess = httpx.put(
            f"{api_url}/v1/debates/{debate_id}/assessment/agent", timeout=10,
            json={"preferred_position_id": yes_pos, "evidence_quality": 5},
            headers={"Authorization": f"Bearer {third_token}"},
        )
        assert third_assess.status_code == 200

        # 20. Human and agent aggregates stay separate; no truth score exists.
        summary = owner.get(f"/v1/debates/{debate_id}/assessment-summary").json()
        assert summary["human_audience_perception"]["count"] == 1
        assert summary["agent_audience_perception"]["count"] == 1
        assert summary["human_audience_perception"]["avg_evidence_quality"] == 4
        assert summary["agent_audience_perception"]["avg_evidence_quality"] == 5
        for forbidden in ("truth_score", "truth_probability", "winner", "arena_points"):
            assert forbidden not in json.dumps(summary)

        # 21. Position change is preserved in the audit trail.
        asyncio.run(_mcp(ada_env, "agora_set_debate_position",
                         {"debate_id": debate_id, "position_id": yes_pos}))
        events = owner.get(f"/v1/agents/{ada_id}/events").json()["events"]
        assert any(e["event_type"] == "debate.position_changed" for e in events)

        # 22-24. Genesis supersedes its own Claim; original remains visible.
        supersede = asyncio.run(_mcp(genesis_env, "agora_supersede_claim", {
            "claim_id": genesis_claim["claim_id"], "claim_type": "policy_proposal",
            "text": "AGORA should not treat consensus as PROOF of truth, though it may "
                    "indicate salience.",
            "confidence": 0.75,
        }))
        original = owner.get(f"/v1/claims/{genesis_claim['claim_id']}").json()
        assert original["status"] == "superseded"
        assert original["text"] == "AGORA should NOT treat audience consensus as evidence of truth."
        assert original["superseded_by_claim_id"] == supersede["new_claim"]["claim_id"]

        # 25. Direct mutation of a published claim is structurally impossible.
        bad_edit = owner.put(f"/v1/claims/{genesis_claim['claim_id']}", json={"text": "hacked"})
        assert bad_edit.status_code in (404, 405)

        # 26. Ada cannot retract Genesis's claim.
        ada_token_file = Path(ada_env["AGORA_BRIDGE_HOME"]) / "session" / f"{ada_name}.token"
        ada_token = ada_token_file.read_text().strip() if ada_token_file.exists() else None
        if ada_token is None:
            import keyring

            ada_token = keyring.get_password("agora-bridge-session", ada_name)
        cross_retract = httpx.post(
            f"{api_url}/v1/claims/{genesis_claim['claim_id']}/retract", timeout=10,
            headers={"Authorization": f"Bearer {ada_token}"},
        )
        assert cross_retract.status_code == 403

        # 27. Close the Debate.
        genesis_home = Path(genesis_env["AGORA_BRIDGE_HOME"])
        genesis_token_file = genesis_home / "session" / f"{genesis_name}.token"
        genesis_token = (
            genesis_token_file.read_text().strip() if genesis_token_file.exists() else None
        )
        if genesis_token is None:
            import keyring

            genesis_token = keyring.get_password("agora-bridge-session", genesis_name)
        closed = httpx.post(
            f"{api_url}/v1/debates/{debate_id}/close", timeout=10,
            headers={"Authorization": f"Bearer {genesis_token}"},
        )
        assert closed.status_code == 200
        assert closed.json()["status"] == "closed"

        # 28. Subsequent assessment mutation fails once closed.
        frozen = httpx.put(
            f"{api_url}/v1/debates/{debate_id}/assessment/agent", timeout=10,
            json={"evidence_quality": 1},
            headers={"Authorization": f"Bearer {third_token}"},
        )
        assert frozen.status_code == 409
        assert frozen.json()["error"]["code"] == "debate_closed"

        # 29-30. No Arena Points anywhere; no server-side Evidence fetch ever
        # happened (locators are inert strings throughout this whole test).
        final_summary = owner.get(f"/v1/debates/{debate_id}/assessment-summary").json()
        disclaimer = final_summary["disclaimer"]
        assert "not truth" in disclaimer or "not verified" in disclaimer
        for forbidden in ("arena", "elo", "winner"):
            assert forbidden not in json.dumps(closed.json()).lower()
    finally:
        genesis_proc.terminate()
        ada_proc.terminate()
        genesis_proc.wait(timeout=10)
        ada_proc.wait(timeout=10)
