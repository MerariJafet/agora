import json

from jsonschema import Draft202012Validator

from scripts.institutional_validator_pilot import (
    MODEL_REVIEW_SCHEMA,
    normalize_model_review,
    parse_claude_result,
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
