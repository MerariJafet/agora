"""Artifact-backed regressions for the actual LLM/API to native handoff checker.

These tests use recorded public TEST evidence, never invoke providers or live APIs.
Source-free installations explicitly skip; the frozen evidence campaign must run them.
"""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "audit/v03/agents/20260909222445-13019"
spec = importlib.util.spec_from_file_location(
    "v03_science_adapter_test", ROOT / "native/tools/v03_scientific_network.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def handoff():
    if not (SOURCE / "results.json").exists():
        pytest.skip("Requires frozen public LLM/API campaign artifact 20260909222445-13019")
    report = json.loads((SOURCE / "results.json").read_text())
    campaign = json.loads((SOURCE / "llm/campaign.json").read_text())
    events = json.loads((SOURCE / "api-protocol-events.json").read_text())
    profiles = {
        e["response"]["actor_id"]: e["response"]
        for e in events
        if e.get("path") == "/v1/research-protocol/institutional-validators"
    }
    case = copy.deepcopy(report["cases"]["LLM-SCI-002"])
    for review in case["reviews"]:
        review["validator_id"] = profiles[review["agora_agent_id"]]["validator_id"]
    return case, report["identities"], campaign


def test_authentic_completed_handoff_verifies(handoff):
    assert module.verify_handoff(*handoff)["integrity_verified"] is True


def test_unsigned_review_verdict_cannot_override_signed_negative_review(handoff):
    case, identities, campaign = handoff
    for review in case["reviews"]:
        assert review["payload"]["verdict"] == "REJECTED"
        review["llm_contribution"]["verdict"] = "APPROVE"
        review["llm_contribution"]["public_conclusion"] = "TAMPERED approval"
    with pytest.raises(ValueError):
        module.verify_handoff(case, identities, campaign)


def test_unsigned_node_payload_cannot_diverge_from_frozen_candidate(handoff):
    case, identities, campaign = handoff
    case["nodes"][0]["payload"]["contribution"]["public_conclusion"] = "TAMPERED research"
    with pytest.raises(ValueError):
        module.verify_handoff(case, identities, campaign)


def test_campaign_contribution_cannot_replace_signed_api_candidate(handoff):
    case, identities, campaign = handoff
    role = case["nodes"][0]["role"]
    c = next(
        c for c in campaign["agents"][role]["contributions"] if c["experiment_id"] == "LLM-SCI-002"
    )
    c["public_conclusion"] = "TAMPERED campaign output"
    with pytest.raises(ValueError):
        module.verify_handoff(case, identities, campaign)


def test_tool_artifacts_cannot_be_swapped_after_api_commitment(handoff):
    case, identities, campaign = handoff
    node = next(n for n in case["nodes"] if n["payload"]["tools"])
    node["payload"]["tools"][0]["result"] = {"fabricated": True}
    with pytest.raises(ValueError):
        module.verify_handoff(case, identities, campaign)


def test_api_author_must_match_persistent_identity(handoff):
    case, identities, campaign = handoff
    case["nodes"][0]["author_agent_id"] = "TAMPERED-AUTHOR"
    with pytest.raises(ValueError):
        module.verify_handoff(case, identities, campaign)
