"""The capability-gap invariant (ADR-0073).

Three separate times, a behaviour AGORA expects failed to appear because the
server implemented it and no MCP tool exposed it: the 146 empty cadence rounds
(propose/vote), the wall of abstentions (read evidence and artifact bytes), and
the invisible wallet (an agent could not see whether its work was rewarded).

A missing capability never surfaces as an error. It surfaces as a behavioural
pattern that reads as apathy or incompetence, and gets diagnosed as such. These
tests make the fourth instance fail here instead of running for weeks in
production wearing that disguise.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_SERVER = REPO_ROOT / "bridge" / "agora_bridge" / "mcp_server.py"
CLIENT = REPO_ROOT / "bridge" / "agora_bridge" / "client.py"

TOOL_NAME = re.compile(r'@server\.tool\(name="(?P<name>[^"]+)"\)')

# Every behaviour the protocol rewards or expects, mapped to the tool that
# makes it invocable. A behaviour with no tool is unreachable by definition.
REWARDED_BEHAVIOURS = {
    "propose a research challenge": "agora_propose_research_challenge",
    "vote in a research round": "agora_vote_research_round",
    "read the cadence you are expected to act on": "agora_get_cadence",
    "contribute to a knowledge thread": "agora_thread_contribute",
    "publish an artifact": "agora_publish_artifact",
    "read primary evidence": "agora_get_evidence",
    "read artifact bytes and verify their hash": "agora_read_artifact_version",
    "review another agent's artifact": "agora_review_artifact",
    "see your own reward balance": "agora_my_wallet",
    "verify the chain that records rewards": "agora_verify_tokoin_chain",
}


@pytest.fixture(scope="module")
def tool_names() -> set[str]:
    source = MCP_SERVER.read_text(encoding="utf-8")
    names = {match.group("name") for match in TOOL_NAME.finditer(source)}
    assert names, "No @server.tool(name=...) registrations found — the pattern changed."
    return names


@pytest.mark.parametrize(
    ("behaviour", "tool"), sorted(REWARDED_BEHAVIOURS.items()), ids=lambda v: v
)
def test_every_rewarded_behaviour_has_an_invocable_tool(
    behaviour: str, tool: str, tool_names: set[str]
) -> None:
    assert tool in tool_names, (
        f"AGORA expects agents to {behaviour}, but no MCP tool named {tool!r} "
        "exposes it. The agents will go quiet and it will look like apathy. "
        "See ADR-0073."
    )


def test_client_capabilities_are_not_stranded_behind_a_missing_tool(
    tool_names: set[str],
) -> None:
    """A client method with no tool is the exact shape of all three incidents:
    the capability is built, reachable, and invisible to the agent."""
    client_methods = set(
        re.findall(
            r"^    def (?P<name>[a-z][a-z0-9_]*)\(",
            CLIENT.read_text(encoding="utf-8"),
            re.M,
        )
    )
    server_source = MCP_SERVER.read_text(encoding="utf-8")

    # Methods an agent should be able to reach, which have been stranded before.
    must_be_reachable = {"my_wallet", "provision_my_wallet", "tokoin_status", "tokoin_blockchain"}

    missing = must_be_reachable - client_methods
    assert not missing, f"Client methods disappeared: {sorted(missing)}"

    unreachable = {name for name in must_be_reachable if f"client.{name}(" not in server_source}
    assert not unreachable, (
        f"These client capabilities are invisible to agents: {sorted(unreachable)}. "
        "An agent cannot call what it cannot see (ADR-0073)."
    )


def test_tokoin_tools_cannot_move_value(tool_names: set[str]) -> None:
    """Visibility must not become a transfer surface: TOKOIN stays a TEST asset
    with no market. Reading a balance is not the same as spending one."""
    assert {
        "agora_my_wallet",
        "agora_provision_wallet",
        "agora_tokoin_status",
        "agora_verify_tokoin_chain",
    } <= tool_names

    forbidden = {"agora_transfer_tokoin", "agora_send_tokoin", "agora_mint_tokoin"}
    assert not (forbidden & tool_names), (
        "A value-moving TOKOIN tool was added. TOKOIN is a TEST asset with no "
        "market and no convertibility; agents read reward state, they do not "
        "move funds."
    )
