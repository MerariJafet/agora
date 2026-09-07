from types import SimpleNamespace

from agora_api.research_protocol_service import (
    REWARD_PERCENT,
    WEIGHTS_BPS,
    _dimensions_for,
    _largest_remainder,
    review_signing_payload,
)


def test_reward_policy_is_exactly_one_hundred_percent():
    assert REWARD_PERCENT == {
        "research_proposer": 1,
        "final_solution": 10,
        "participant_contribution_pool": 60,
        "institutional_validation_pool": 20,
        "agora_infrastructure": 9,
    }
    assert sum(REWARD_PERCENT.values()) == 100
    assert sum(WEIGHTS_BPS.values()) == 10_000


def test_largest_remainder_is_exact_and_deterministic():
    result = _largest_remainder(10, {"agent-c": 1, "agent-a": 1, "agent-b": 1})
    assert result == {"agent-c": 3, "agent-a": 4, "agent-b": 3}
    assert sum(result.values()) == 10


def test_refutation_and_negative_findings_receive_scientific_credit():
    row = SimpleNamespace(
        object_type="refutation",
        state="SUPPORTED_ONCE",
        rights_status="explicit_open_license",
    )
    dimensions = _dimensions_for(row, inbound=2, validation=1)
    assert dimensions["error_detection_value"] == 1000
    assert dimensions["correctness"] == 700
    assert dimensions["downstream_dependency"] > 0


def test_message_volume_and_votes_are_not_scoring_inputs():
    row = SimpleNamespace(
        object_type="hypothesis",
        state="PROPOSED",
        rights_status="explicit_open_license",
    )
    dimensions = _dimensions_for(row, inbound=0, validation=0)
    assert "messages" not in dimensions
    assert "votes" not in dimensions
    assert "time_connected" not in dimensions
    assert "popularity" not in dimensions


def test_institutional_signature_payload_binds_exact_candidate_hash():
    candidate = SimpleNamespace(candidate_id="rcs_test", content_hash="a" * 64)
    payload = {
        "institution_id": "ins_test",
        "verdict": "APPROVED",
        "methodology_review": "method",
        "evidence_review": "evidence",
        "paper_review": "paper",
        "experiment_review": "experiment",
        "conflict_declaration": "none",
    }
    signed = review_signing_payload(candidate, payload)
    assert signed["candidate_id"] == "rcs_test"
    assert signed["candidate_content_hash"] == "a" * 64
    assert signed["domain"] == "agora.institutional.review.v1"
