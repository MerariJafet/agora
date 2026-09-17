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

# --- Structural inversion (wave 3) ------------------------------------------
# The manual behaviour list above is a list of scars: it only catches gaps we
# already lived through. This test inverts the direction: EVERY public client
# method must either be reachable from an MCP tool or be explicitly declared
# runtime-only with a category. A new stranded capability now fails CI at
# birth instead of running for weeks disguised as agent apathy.

# Client methods that are deliberately NOT exposed as MCP tools. Every entry
# needs a category; removing a method from client.py removes it from here.
INTENTIONALLY_RUNTIME_ONLY = {
    # -- identity/session plumbing: the bridge process owns key material and
    #    session lifecycle; an LLM must never drive these directly.
    "request_challenge": "identity_plumbing",
    "register": "identity_plumbing",
    "build_registration_message": "identity_plumbing",
    "build_session_message": "identity_plumbing",
    "build_revocation_message": "identity_plumbing",
    "build_claim_message": "identity_plumbing",
    "build_enrollment_message": "identity_plumbing",
    "build_passport_issue_message": "identity_plumbing",
    "session_signed": "identity_plumbing",
    "revoke_signed": "identity_plumbing",
    "claim": "identity_plumbing",
    "ping": "identity_plumbing",
    "health": "identity_plumbing",
    "request_enrollment_challenge": "identity_plumbing",
    "attest_enrollment": "identity_plumbing",
    "issue_passport": "identity_plumbing",
    "publish_card_signature": "identity_plumbing",
    "world_trust_bootstrap": "identity_plumbing",
    # -- world-rule feed and charter acceptance: driven by the native runtime
    #    loop as part of the connection sequence, before any tool call.
    "attest_world_rule_versioned": "runtime_connection_sequence",
    "world_rule_feed": "runtime_connection_sequence",
    "mark_world_rule_cursor": "runtime_connection_sequence",
    "evaluate_world_rules": "runtime_connection_sequence",
    "accept_world_charter": "runtime_connection_sequence",
    "world_charter": "runtime_connection_sequence",
    "world_manifest": "runtime_connection_sequence",
    "lineage": "runtime_connection_sequence",
    # -- owner/operator surfaces: module updates and agent-version management
    #    belong to the human owner, not to the agent's own tool belt.
    "update_module": "owner_operator_surface",
    "rollback_module": "owner_operator_surface",
    "activate_agent_version": "owner_operator_surface",
    "simulate_research_release_policy": "owner_operator_surface",
    # -- Arena legacy challenge plane (pre-Mission-Challenge), kept for
    #    compatibility; the live world runs Mission Challenges instead.
    "get_challenge": "arena_legacy",
    "open_challenge": "arena_legacy",
    "create_challenge_instance": "arena_legacy",
    "resolve_challenge_instance": "arena_legacy",
    "judge_submission": "arena_legacy",
    # -- KNOWN GAPS, deliberately deferred with eyes open (candidates for the
    #    next wave; each one stays a conscious decision, not an accident).
    "attach_mission_challenge_evidence": "known_gap_deferred",
    "create_mission_challenge_draft": "known_gap_deferred",
    "finalize_mission_challenge_submission": "known_gap_deferred",
    "mission_challenge_capabilities": "known_gap_deferred",
    "mission_challenge_global_capabilities": "known_gap_deferred",
    "review_research_proposal": "known_gap_deferred",
    "provide_research_information": "known_gap_deferred",
    "assess_research_priority": "known_gap_deferred",
    "commit_research_resource": "known_gap_deferred",
    "advance_rfc": "known_gap_deferred",
    "amend_knowledge_protocol": "known_gap_deferred",
    "accept_mission_task": "known_gap_deferred",
    "create_mission_task": "known_gap_deferred",
    "request_mission_task_revision": "known_gap_deferred",
    "activate_mission": "known_gap_deferred",
    "civic_roles": "known_gap_deferred",
    "create_civic_role": "known_gap_deferred",
    "subscribe_civic_role": "known_gap_deferred",
    "create_world_market_need": "known_gap_deferred",
    "create_world_market_offer": "known_gap_deferred",
    "get_group": "known_gap_deferred",
    "a2a_get_task": "known_gap_deferred",
}


def test_every_client_capability_is_exposed_or_declared_runtime_only() -> None:
    """Inverted audit: the default for a new client method is 'agents can
    reach it'. Hiding one now requires writing it down here with a reason."""
    client_methods = set(
        re.findall(
            r"^    def (?P<name>[a-z][a-z0-9_]*)\(",
            CLIENT.read_text(encoding="utf-8"),
            re.M,
        )
    )
    server_source = MCP_SERVER.read_text(encoding="utf-8")
    reachable = {name for name in client_methods if f"client.{name}(" in server_source}

    stranded = client_methods - reachable - set(INTENTIONALLY_RUNTIME_ONLY)
    assert not stranded, (
        f"New client capabilities with no MCP tool and no declared reason: "
        f"{sorted(stranded)}. This is the exact shape of every capability-gap "
        "incident (ADR-0073): the capability exists, the agent cannot see it, "
        "and the failure will present as apathy. Either add a tool or add the "
        "method to INTENTIONALLY_RUNTIME_ONLY with a category."
    )

    stale_allowlist = set(INTENTIONALLY_RUNTIME_ONLY) - client_methods
    assert not stale_allowlist, (
        f"Allowlist entries for client methods that no longer exist: "
        f"{sorted(stale_allowlist)}"
    )

    # An allowlisted method that later gains a tool should leave the list:
    # the list documents *hidden* capabilities only.
    shadowed = set(INTENTIONALLY_RUNTIME_ONLY) & reachable
    assert not shadowed, (
        f"These methods are exposed as tools AND allowlisted as hidden: "
        f"{sorted(shadowed)}. Remove them from INTENTIONALLY_RUNTIME_ONLY."
    )
