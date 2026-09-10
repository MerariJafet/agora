"""Explicit TEST-only pilot fixtures; no real institutions or experiment outputs."""

from copy import deepcopy

import pytest

from scripts.evaluate_pilot_results import ARMS, digest, evaluate


def fixture():
    budget = {"max_cost_usd": 5, "max_tokens": 1000, "max_wall_seconds": 60}
    plan = {
        "schema": "agora-pilot-plan.v1",
        "study_status": "PREREGISTERED",
        "preregistration_reference": "TEST_ONLY://not-a-real-preregistration",
        "task_ids": ["TEST_task"],
        "equal_budget_per_run": budget,
        "assignments": [
            {
                "run_id": f"TEST_run_{i}",
                "task_id": "TEST_task",
                "arm": arm,
                "owner_ids": ["TEST_owner"],
                "budget": budget.copy(),
            }
            for i, arm in enumerate(ARMS)
        ],
        "reviewer_registry": [
            {
                "reviewer_id": "TEST_reviewer",
                "owner_id": "TEST_external",
                "identity_verification_reference": "TEST_ONLY://synthetic-identity",
                "independence_evidence_reference": "TEST_ONLY://synthetic-independence",
            }
        ],
    }
    results = {"schema": "agora-pilot-results.v1", "plan_sha256": digest(plan), "runs": []}
    reviews = {"schema": "agora-pilot-reviews.v1", "plan_sha256": digest(plan), "reviews": []}
    return plan, results, reviews


def test_missing_runs_remain_denominator_and_cost_is_unknown():
    plan, results, reviews = fixture()
    report = evaluate(plan, results, reviews)
    for arm in ARMS:
        m = report["arms"][arm]
        assert m["planned_runs"] == m["missing_runs"] == m["cost_unknown_runs"] == 1
        assert m["correct_fraction_of_all_planned_runs"] == 0
    assert not report["inferential_superiority_claim"]


def test_complete_reviewed_data_counts_negative_runs_and_costs():
    plan, results, reviews = fixture()
    for i in range(3):
        run = {
            "run_id": f"TEST_run_{i}",
            "status": "completed" if i != 1 else "failed",
            "cost_usd": 2,
            "tokens": 500,
            "wall_seconds": 25,
            "result_artifact_sha256": "a" * 64,
        }
        results["runs"].append(run)
        reviews["reviews"].append(
            {
                "run_id": run["run_id"],
                "reviewer_id": "TEST_reviewer",
                "reviewed_result_sha256": digest(run),
                "verdict": "correct" if i == 0 else "incorrect",
                "review_evidence_sha256": "b" * 64,
                "review_evidence_reference": "TEST_ONLY://review",
            }
        )
    report = evaluate(plan, results, reviews)
    assert report["arms"]["single-agent"]["correct_per_registered_review"] == 1
    failed = report["arms"]["conventional-multi-agent"]
    assert failed["failed_runs"] == 1 and failed["reported_cost_usd_sum"] == 2
    assert not report["reviewer_identity_verified_by_evaluator"]


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate",
        "negative_cost",
        "self_report",
        "unregistered",
        "same_owner",
        "wrong_hash",
        "changed_budget",
    ],
)
def test_reject_invalid_or_nonindependent_evidence(problem):
    plan, results, reviews = fixture()
    run = {
        "run_id": "TEST_run_0",
        "status": "completed",
        "cost_usd": 1,
        "tokens": 1,
        "wall_seconds": 1,
        "result_artifact_sha256": "a" * 64,
    }
    results["runs"] = [run]
    review = {
        "run_id": run["run_id"],
        "reviewer_id": "TEST_reviewer",
        "reviewed_result_sha256": digest(run),
        "verdict": "correct",
        "review_evidence_sha256": "b" * 64,
        "review_evidence_reference": "TEST_ONLY://review",
    }
    reviews["reviews"] = [review]
    if problem == "duplicate":
        results["runs"].append(deepcopy(run))
    elif problem == "negative_cost":
        run["cost_usd"] = -1
    elif problem == "self_report":
        run["verified"] = True
    elif problem == "unregistered":
        review["reviewer_id"] = "UNKNOWN"
    elif problem == "same_owner":
        plan["reviewer_registry"][0]["owner_id"] = "TEST_owner"
    elif problem == "wrong_hash":
        review["reviewed_result_sha256"] = "0" * 64
    else:
        plan["assignments"][0]["budget"]["max_cost_usd"] = 9
    results["plan_sha256"] = reviews["plan_sha256"] = digest(plan)
    with pytest.raises(ValueError):
        evaluate(plan, results, reviews)


def test_result_without_external_review_never_counts_as_correct():
    plan, results, reviews = fixture()
    results["runs"] = [
        {
            "run_id": "TEST_run_0",
            "status": "completed",
            "cost_usd": 1,
            "result_artifact_sha256": "a" * 64,
        }
    ]
    m = evaluate(plan, results, reviews)["arms"]["single-agent"]
    assert m["completed_runs"] == 1
    assert m["correct_per_registered_review"] == 0
    assert m["tokens_unknown_runs"] == 1
