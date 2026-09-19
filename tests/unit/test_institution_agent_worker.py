"""The delegated Agent worker must not turn model claims into test evidence."""

import json

import pytest
from agora_api.magna_knowledge_ledger import canonical_json_hash

from scripts.institution_agent_worker import (
    PROPOSAL_VALIDATOR,
    _proposal_payload,
    _reproduction_receipt,
)


def _package() -> dict:
    return {
        "candidate": {"candidate_id": "rcs_fixture", "content_hash": "a" * 64},
        "institution_agent": {"institution_id": "ins_fixture"},
        "submission": {"author_agent_id": "agt_author", "team_agent_ids": []},
        "final_solution": {"object_id": "mko_solution"},
        "review_context": {
            "context_hash": "b" * 64,
            "participants": [],
            "challenge_thread": [],
            "world_conversation": [],
            "forum_conversation": [],
            "audit_events": [],
            "artifacts": [],
            "evidence": [],
            "reward_context": {"total_aceros": 100},
        },
    }


def _model_output() -> dict:
    return {
        "review": {
            "verdict": "APPROVED",
            "methodology_review": "The claimed method appears internally consistent in the text.",
            "evidence_review": "The public evidence was assessed only from metadata.",
            "paper_review": "The candidate manuscript describes a bounded claim with caveats.",
            "experiment_review": "I ran all experiments and reproduced the result.",
            "conflict_declaration": "No declared conflict.",
        },
        "recommendation": {
            "assessment": "PASS",
            "rationale": "The candidate is approved after my claimed independent reproduction.",
            "blocking_issues": [],
            "what_is_missing": [],
            "suggested_actions": [],
        },
        "allocations": [
            {
                "recipient_kind": "AGENT",
                "recipient_id": "agt_unknown",
                "amount_aceros": 100,
                "basis": "Unjustified model-invented contributor allocation.",
            }
        ],
    }


def test_model_claim_without_receipt_cannot_become_approval() -> None:
    proposal = _proposal_payload(_package(), _model_output(), None, None)
    PROPOSAL_VALIDATOR.validate(proposal)
    assert proposal["review"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "No independent experiment" in proposal["review"]["experiment_review"]
    assert proposal["evidence_manifest"]["test_receipt_hashes"] == []
    assert proposal["tokoin_recommendation"]["allocations"][0]["recipient_kind"] == "RESERVE"
    assert proposal["tokoin_recommendation"]["settlement_eligible"] is False


def test_reproduction_receipt_is_candidate_bound_and_inspectable(tmp_path) -> None:
    package = _package()
    receipt = {
        "candidate_id": "rcs_fixture",
        "candidate_content_hash": "a" * 64,
        "reproduction_status": "REPRODUCED",
        "tests_executed": [{"name": "independent fixture check", "passed": True}],
    }
    path = tmp_path / "rcs_fixture.json"
    path.write_text(json.dumps(receipt))
    read, receipt_hash = _reproduction_receipt(path, package)
    assert read == receipt
    assert receipt_hash == canonical_json_hash(
        receipt, domain="agora.institution.agent.reproduction_receipt.v1"
    )
    proposal = _proposal_payload(package, _model_output(), read, receipt_hash)
    assert proposal["reproduction_receipt"] == receipt
    assert proposal["evidence_manifest"]["test_receipt_hashes"] == [receipt_hash]
    package["candidate"]["content_hash"] = "c" * 64
    with pytest.raises(RuntimeError, match="does not match"):
        _reproduction_receipt(path, package)
