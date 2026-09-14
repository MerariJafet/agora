import json

from jsonschema import Draft202012Validator

from scripts.institutional_validator_pilot import (
    MODEL_REVIEW_SCHEMA,
    _joint_candidate_ids,
    _owner_recommendation,
    _tokoin_recommendation,
    normalize_model_review,
    parse_claude_result,
    run_reproduction,
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
