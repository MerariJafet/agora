import json

import pytest
from agora_api.magna_knowledge_ledger import canonical_json_hash
from jsonschema import Draft202012Validator

from scripts.institutional_validator_pilot import (
    MODEL_REVIEW_SCHEMA,
    _joint_candidate_ids,
    _owner_recommendation,
    _tokoin_recommendation,
    bind_review_to_executed_evidence,
    normalize_model_review,
    parse_claude_result,
    run_reproduction,
    validation_queue,
    verify_review_context,
    watch_assignments,
)


def _review() -> dict:
    return {
        "verdict": "APPROVED",
        "confidence": 95,
        "reproduction_status": "FULL_INDEPENDENT_REPRODUCTION",
        "dimensions": {
            "question_validity": 5,
            "methodology": 5,
            "evidence_quality": 5,
            "reproducibility": 5,
            "falsifiability": 5,
            "statistical_rigor": 4,
            "code_integrity": 5,
            "data_integrity": 5,
            "literature_alignment": 4,
            "claim_scope": 5,
        },
        "summary": "The bounded arithmetic claim was independently reproduced.",
        "methodology_findings": "The method directly tests the stated bounded claim.",
        "reproduction_findings": "Independent formulations returned the expected result.",
        "evidence_findings": "The supplied evidence supports only the stated scope.",
        "critical_issues": [],
        "minor_issues": [],
        "requested_changes": [],
        "executed_tests": ["Iterative and closed-form calculations matched."],
        "artifacts_reviewed": ["candidate-package.json", "reproduction.json"],
    }


def test_parse_claude_result_accepts_structured_output_and_fenced_result() -> None:
    review = _review()
    assert parse_claude_result(json.dumps({"structured_output": review})) == review
    fenced = {"result": f"```json\n{json.dumps(review)}\n```"}
    assert parse_claude_result(json.dumps(fenced)) == review


def test_normalize_model_review_maps_only_documented_aliases() -> None:
    normalized = normalize_model_review(_review())

    assert normalized["confidence"] == 95
    assert normalized["reproduction_status"] == "REPRODUCED"
    assert normalized["dimensions"]["evidence"] == 5
    assert normalized["dimensions"]["statistics"] == 4
    assert "evidence_quality" not in normalized["dimensions"]
    assert not list(Draft202012Validator(MODEL_REVIEW_SCHEMA).iter_errors(normalized))


def test_normalize_model_review_does_not_accept_unknown_status() -> None:
    review = _review()
    review["reproduction_status"] = "UNVERIFIED_NEW_STATUS"

    normalized = normalize_model_review(review)

    assert normalized["reproduction_status"] == "UNVERIFIED_NEW_STATUS"
    assert list(Draft202012Validator(MODEL_REVIEW_SCHEMA).iter_errors(normalized))


def test_owner_recommendation_preserves_blockers_and_missing_work() -> None:
    review = _review()
    review.update(
        {
            "verdict": "REQUIRES_REVISION",
            "critical_issues": ["The primary result has no independent receipt."],
            "requested_changes": ["Attach and rerun the deterministic test."],
        }
    )

    recommendation = _owner_recommendation(review)

    assert recommendation == {
        "assessment": "PASS_WITH_CONDITIONS",
        "rationale": review["summary"],
        "blocking_issues": review["critical_issues"],
        "what_is_missing": review["requested_changes"],
        "suggested_actions": review["requested_changes"],
    }


def test_tokoin_recommendation_is_exact_and_never_settleable() -> None:
    package = {
        "review_context": {
            "reward_context": {
                "total_aceros": 1_000,
                "allocation": {
                    "pools": {"institutional_validation_pool": 200},
                    "research_proposer": [
                        {"actor_id": "agent.proposer", "amount_aceros": 100}
                    ],
                    "final_solution": [
                        {"actor_id": "agent.author", "amount_aceros": 200}
                    ],
                    "participant_contribution_pool": [
                        {"actor_id": "agent.peer", "amount_aceros": 350}
                    ],
                    "agora_infrastructure": [
                        {"actor_id": "system.agora", "amount_aceros": 100}
                    ],
                    "reserved_unallocated": {
                        "participant_contribution_pool": 50
                    },
                },
            }
        }
    }

    recommendation = _tokoin_recommendation(package, "agent.validator-a")

    assert recommendation["synthetic_test_only"] is True
    assert recommendation["settlement_eligible"] is False
    assert recommendation["requires_separate_human_validation"] is True
    assert sum(
        row["amount_aceros"] for row in recommendation["allocations"]
    ) == 1_000
    assert {
        (row["recipient_kind"], row["recipient_id"], row["amount_aceros"])
        for row in recommendation["allocations"]
    } >= {
        ("TEST_VALIDATOR_CREDIT", "agent.validator-a", 100),
        ("RESERVE", "PEER_VALIDATOR_TEST_CREDIT_RESERVE", 100),
        ("RESERVE", "PARTICIPANT_CONTRIBUTION_TEST_RESERVE", 50),
    }


def test_joint_candidate_discovery_requires_two_live_assignments() -> None:
    assignments = [
        [
            {"candidate_id": "joint", "revealed": False, "state": "ASSIGNED"},
            {"candidate_id": "codex-only", "revealed": False, "state": "ASSIGNED"},
            {
                "candidate_id": "conflicted",
                "revealed": False,
                "state": "CONFLICT_DECLARED",
            },
        ],
        [
            {"candidate_id": "joint", "revealed": False, "state": "ASSIGNED"},
            {"candidate_id": "conflicted", "revealed": False, "state": "ASSIGNED"},
            {"candidate_id": "finished", "revealed": True, "state": "VERDICT_REVEALED"},
        ],
    ]

    assert _joint_candidate_ids(assignments) == ["joint"]


def test_unknown_protocol_gets_static_audit_without_executing_candidate_code(
    tmp_path,
) -> None:
    home = tmp_path / "validator"
    (home / "artifacts").mkdir(parents=True)
    package_path = home / "candidate.json"
    package_path.write_text(
        json.dumps(
            {
                "candidate": {"candidate_id": "candidate-x", "content_hash": "a" * 64},
                "final_solution": {
                    "payload": {
                        "protocol_id": "untrusted-arbitrary-protocol",
                        "command": "never-run-this",
                    }
                },
                "review_context": {
                    "context_hash": "b" * 64,
                    "private_service_logs_disclosed": False,
                    "participants": [],
                    "challenge_thread": [],
                    "world_conversation": [],
                    "forum_conversation": [],
                    "audit_events": [],
                    "artifacts": [],
                    "evidence": [],
                },
            }
        )
    )

    evidence = run_reproduction(home, package_path)

    assert evidence["adapter"] == "static-context-integrity-v1"
    assert evidence["protocol_adapter_supported"] is False
    assert evidence["candidate_code_executed"] is False
    assert evidence["reproduced"] is False
    assert (
        evidence["reproduction_status_hint"]
        == "NOT_REPRODUCIBLE_FROM_PROVIDED_ARTIFACTS"
    )


def test_evidence_gate_demotes_unreproduced_model_approval() -> None:
    review = normalize_model_review(_review())
    evidence = {
        "candidate_id": "candidate-x",
        "tests_executed": ["Checked the package structure only."],
        "reproduction_status_hint": "NOT_REPRODUCIBLE_FROM_PROVIDED_ARTIFACTS",
    }

    result = bind_review_to_executed_evidence(review, evidence)

    assert result["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["confidence"] == 50
    assert result["reproduction_status"] == evidence["reproduction_status_hint"]
    assert result["executed_tests"] == evidence["tests_executed"]
    assert result["artifacts_reviewed"] == [
        "candidate-candidate-x.json", "reproduction-candidate-x.json"
    ]
    assert result["critical_issues"]
    assert result["requested_changes"]


def test_review_context_hash_rejects_modified_conversation() -> None:
    context = {
        "participants": [],
        "world_conversation": [{"message_id": "msg-1", "content": "original"}],
        "private_service_logs_disclosed": False,
    }
    context["context_hash"] = canonical_json_hash(
        context, domain="agora.institutional.validator.context.v1"
    )
    package = {"review_context": context}
    verify_review_context(package)

    context["world_conversation"][0]["content"] = "modified"
    with pytest.raises(RuntimeError, match="context hash mismatch"):
        verify_review_context(package)


def test_allowlisted_adapter_limits_untrusted_workload(tmp_path) -> None:
    home = tmp_path / "validator"
    (home / "artifacts").mkdir(parents=True)
    package_path = home / "candidate.json"
    package_path.write_text(
        json.dumps(
            {
                "candidate": {"candidate_id": "candidate-large", "content_hash": "a" * 64},
                "final_solution": {
                    "payload": {
                        "protocol_id": "sum-of-squares-v1",
                        "inputs": {"start": 1, "end": 10_000_000},
                        "expected_output": 1,
                    }
                },
                "review_context": {"context_hash": "b" * 64},
            }
        )
    )

    evidence = run_reproduction(home, package_path)

    assert evidence["reproduced"] is False
    assert evidence["reproduction_status_hint"] == "NOT_REPRODUCED_DUE_TO_TOOL_LIMITATION"
    assert evidence["candidate_code_executed"] is False


def test_watch_reports_unassigned_queue_without_review(monkeypatch, tmp_path) -> None:
    import scripts.institutional_validator_pilot as pilot

    queue = {
        "synthetic_test_only": True,
        "awaiting_freeze": [],
        "candidates": [{"candidate_id": "candidate-x", "next_action": "OWNER_ASSIGN_PANEL"}],
    }
    ticks = iter([0.0, 1.0])
    monkeypatch.setattr(pilot, "WATCH_STATE", tmp_path / "watch.json")
    monkeypatch.setattr(pilot, "validation_queue", lambda: queue)
    monkeypatch.setattr(pilot, "assigned_candidate_ids", lambda _url: [])
    monkeypatch.setattr(pilot.time, "monotonic", lambda: next(ticks))

    result = watch_assignments("http://example.test", poll_seconds=1, max_wait_seconds=0.5)

    assert result["idle_no_joint_assignment"] is True
    assert result["queue"] == queue
    assert json.loads((tmp_path / "watch.json").read_text())["candidates"] == queue["candidates"]


def test_queue_disposes_async_pool_between_poll_cycles(monkeypatch) -> None:
    import agora_api.db as db

    import scripts.institutional_validator_pilot as pilot

    calls: list[str] = []

    async def scan() -> dict:
        calls.append("scan")
        return {"candidates": []}

    async def dispose() -> None:
        calls.append("dispose")

    monkeypatch.setattr(pilot, "_validation_queue", scan)
    monkeypatch.setattr(db, "dispose_engine", dispose)

    assert validation_queue() == {"candidates": []}
    assert validation_queue() == {"candidates": []}
    assert calls == ["scan", "dispose", "scan", "dispose"]
