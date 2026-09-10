from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agora_api.mission_challenges_service import _maybe_resolve
from agora_api.science_scope import (
    PRIME_SIEVE_ACCEPTANCE_CONTRACT,
    PRIME_SIEVE_GENESIS_OBJECTIVE,
    _prime_reference,
    assess_solution_scope,
)


def fixtures(experiments, contract=PRIME_SIEVE_ACCEPTANCE_CONTRACT):
    problem = {} if contract is None else {"acceptance_contract": contract}
    return SimpleNamespace(challenge_problem=problem), SimpleNamespace(experiments=experiments)


def test_declared_partial_range_cannot_meet_full_contract():
    count, digest = _prime_reference(500)
    mission, submission = fixtures(
        {"limit": 500, "prime_count": count, "prime_list_sha256": digest}
    )
    assessment = assess_solution_scope(mission, submission)
    assert not assessment["eligible_for_full_resolution"]
    assert "declared_bound_does_not_match_challenge" in assessment["blockers"]


def test_matching_result_is_not_execution_or_truth_attestation():
    count, digest = _prime_reference(10000)
    mission, submission = fixtures(
        {"limit": 10000, "prime_count": count, "prime_list_sha256": digest}
    )
    assert count == 1229
    result = assess_solution_scope(mission, submission)
    assert result["eligible_for_full_resolution"]
    assert result["verification_scope"] == "declared_finite_result_not_execution_or_novelty"
    submission.experiments["prime_list_sha256"] = "0" * 64
    assert not assess_solution_scope(mission, submission)["eligible_for_full_resolution"]


@pytest.mark.parametrize(
    "experiments,contract",
    [
        ({"scope_complete": False}, None),
        ({"contribution_kind": "replication_step"}, None),
        ({}, {"version": "unknown"}),
        ({}, {**PRIME_SIEVE_ACCEPTANCE_CONTRACT, "upper_bound_exclusive": 10**10}),
    ],
)
async def test_scope_blocker_never_reaches_votes_or_settlement(experiments, contract):
    mission, submission = fixtures(experiments, contract)
    session = AsyncMock()
    assert not await _maybe_resolve(session, mission=mission, submission=submission, trace_id=None)
    session.execute.assert_not_called()
    assert not session.mock_calls


def test_legacy_is_explicitly_unverified_not_silently_retrofitted():
    result = assess_solution_scope(*fixtures({}, None))
    assert result["status"] == "legacy_unscoped"
    assert not result["verified"]


def legacy_prime():
    return SimpleNamespace(
        challenge_kind="genesis_training",
        objective=PRIME_SIEVE_GENESIS_OBJECTIVE,
        challenge_problem={
            "genesis_sequence": 1,
            "name": "Prime Sieve Reproducibility",
            "status": "training_problem",
        },
    )


async def test_exact_legacy_prime_definition_blocks_500_without_db_mutation():
    mission = legacy_prime()
    before = dict(mission.challenge_problem)
    count, digest = _prime_reference(500)
    submission = SimpleNamespace(
        experiments={
            "limit": 500,
            "prime_count": count,
            "prime_list_sha256": digest,
        }
    )
    result = assess_solution_scope(mission, submission)
    assert result["contract_source"] == "legacy_genesis_definition"
    assert not result["eligible_for_full_resolution"]
    assert mission.challenge_problem == before
    session = AsyncMock()
    assert not await _maybe_resolve(session, mission=mission, submission=submission, trace_id=None)
    assert not session.mock_calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("genesis_sequence", 2),
        ("genesis_sequence", True),
        ("name", "Prime Sieve Clone"),
        ("status", "unknown_version"),
    ],
)
def test_near_matching_prime_definition_never_falls_back_to_unscoped(field, value):
    mission = legacy_prime()
    mission.challenge_problem[field] = value
    result = assess_solution_scope(mission, SimpleNamespace(experiments={}))
    assert result["status"] == "needs_information"
    assert not result["eligible_for_full_resolution"]


def test_legacy_prime_changed_objective_requires_explicit_contract():
    mission = legacy_prime()
    mission.objective = "Find primes below 500."
    result = assess_solution_scope(mission, SimpleNamespace(experiments={}))
    assert result["status"] == "needs_information"
    assert not result["eligible_for_full_resolution"]
