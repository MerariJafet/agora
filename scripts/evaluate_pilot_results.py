#!/usr/bin/env python3
"""Validate a preregistered pilot and report descriptive, denominator-aware metrics.

This does not run agents, infer statistical superiority or verify real-world identity.
"""

import argparse
import hashlib
import json
from pathlib import Path

ARMS = ("single-agent", "conventional-multi-agent", "agora")
STATUSES = {"completed", "failed", "abstained"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonnegative(value):
    import math

    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def evaluate(plan, results, reviews):
    require(plan.get("schema") == "agora-pilot-plan.v1", "Unsupported plan schema")
    require(results.get("schema") == "agora-pilot-results.v1", "Unsupported results schema")
    require(reviews.get("schema") == "agora-pilot-reviews.v1", "Unsupported reviews schema")
    require(results.get("plan_sha256") == digest(plan), "Results must bind the frozen plan hash")
    require(reviews.get("plan_sha256") == digest(plan), "Reviews must bind the frozen plan hash")
    tasks = plan.get("task_ids", [])
    require(tasks and len(tasks) == len(set(tasks)), "Task IDs must be nonempty and unique")
    assignments = plan.get("assignments", [])
    run_ids = [a["run_id"] for a in assignments]
    require(run_ids and len(run_ids) == len(set(run_ids)), "Assignment IDs must be unique")
    budgets = plan["equal_budget_per_run"]
    require(
        set(budgets) == {"max_cost_usd", "max_tokens", "max_wall_seconds"},
        "Provide the three equal budget limits",
    )
    require(all(nonnegative(v) and v > 0 for v in budgets.values()), "Budgets must be positive")
    counts = {}
    assigned = {}
    for a in assignments:
        require(a["arm"] in ARMS and a["task_id"] in tasks, "Unknown arm or task")
        require(
            isinstance(a.get("owner_ids"), list)
            and a["owner_ids"]
            and all(isinstance(x, str) and x for x in a["owner_ids"]),
            "Owner IDs required",
        )
        require(a.get("budget") == budgets, "Each arm must receive the same per-run budget")
        assigned[a["run_id"]] = a
        key = (a["task_id"], a["arm"])
        counts[key] = counts.get(key, 0) + 1
    for task in tasks:
        ns = [counts.get((task, arm), 0) for arm in ARMS]
        require(ns[0] > 0 and len(set(ns)) == 1, "Balance assignments per task across all arms")
    registry = {}
    for reviewer in plan.get("reviewer_registry", []):
        rid = reviewer["reviewer_id"]
        require(rid not in registry, "Duplicate reviewer ID")
        require(
            reviewer.get("owner_id")
            and reviewer.get("identity_verification_reference")
            and reviewer.get("independence_evidence_reference"),
            "Reviewer evidence required",
        )
        registry[rid] = reviewer
    if results.get("runs"):
        require(
            plan.get("study_status") == "PREREGISTERED"
            and bool(plan.get("preregistration_reference")),
            "Recorded runs require a preregistered plan reference",
        )
    runs = {}
    allowed = {"run_id", "status", "cost_usd", "tokens", "wall_seconds", "result_artifact_sha256"}
    for row in results.get("runs", []):
        require(
            set(row) <= allowed, "Unknown result fields: self-reported correctness is not accepted"
        )
        run_id = row["run_id"]
        require(run_id in assigned and run_id not in runs, "Unknown or duplicate result run ID")
        require(row.get("status") in STATUSES, "Unknown run status")
        for field in ("cost_usd", "tokens", "wall_seconds"):
            value = row.get(field)
            require(value is None or nonnegative(value), f"Invalid {field}")
        require(row.get("tokens") is None or type(row["tokens"]) is int, "Tokens must be integer")
        if row["status"] == "completed":
            require(
                valid_hash(row.get("result_artifact_sha256")),
                "Completed result needs artifact hash",
            )
        runs[run_id] = row
    reviewed = {}
    for review in reviews.get("reviews", []):
        rid, run_id = review["reviewer_id"], review["run_id"]
        require(run_id in runs and run_id not in reviewed, "Unknown or duplicate review run ID")
        require(rid in registry, "Reviewer must exist in frozen independent registry")
        require(
            registry[rid]["owner_id"] not in assigned[run_id]["owner_ids"],
            "Same-owner review is not independent",
        )
        require(
            review.get("reviewed_result_sha256") == digest(runs[run_id]),
            "Review does not bind exact run result",
        )
        require(
            review.get("verdict") in {"correct", "incorrect", "insufficient_evidence"},
            "Invalid review verdict",
        )
        require(
            valid_hash(review.get("review_evidence_sha256"))
            and review.get("review_evidence_reference"),
            "Independent review must reference evidence",
        )
        require(
            review["verdict"] != "correct" or runs[run_id]["status"] == "completed",
            "A missing/failed/abstained result cannot count as correct",
        )
        reviewed[run_id] = review
    metrics = {}
    for arm in ARMS:
        ids = [r for r, a in assigned.items() if a["arm"] == arm]
        observed = [runs[r] for r in ids if r in runs]
        accepted = sum(reviewed.get(r, {}).get("verdict") == "correct" for r in ids)
        metrics[arm] = {
            "planned_runs": len(ids),
            "reported_runs": len(observed),
            "missing_runs": len(ids) - len(observed),
            "completed_runs": sum(r["status"] == "completed" for r in observed),
            "failed_runs": sum(r["status"] == "failed" for r in observed),
            "abstained_runs": sum(r["status"] == "abstained" for r in observed),
            "registered_independent_reviews": sum(r in reviewed for r in ids),
            "correct_per_registered_review": accepted,
            "correct_fraction_of_all_planned_runs": accepted / len(ids),
            "reported_cost_usd_sum": sum(r.get("cost_usd") or 0 for r in observed),
            "cost_unknown_runs": sum(r not in runs or runs[r].get("cost_usd") is None for r in ids),
            "reported_tokens_sum": sum(r.get("tokens") or 0 for r in observed),
            "tokens_unknown_runs": sum(r not in runs or runs[r].get("tokens") is None for r in ids),
            "reported_wall_seconds_sum": sum(r.get("wall_seconds") or 0 for r in observed),
            "wall_seconds_unknown_runs": sum(
                r not in runs or runs[r].get("wall_seconds") is None for r in ids
            ),
            "budget_exceeded_runs": sum(
                any(
                    r.get(field) is not None and r[field] > budgets[limit]
                    for field, limit in [
                        ("cost_usd", "max_cost_usd"),
                        ("tokens", "max_tokens"),
                        ("wall_seconds", "max_wall_seconds"),
                    ]
                )
                for r in observed
            ),
        }
    return {
        "schema": "agora-pilot-descriptive-metrics.v1",
        "study_status": plan.get("study_status", "UNKNOWN"),
        "plan_sha256": digest(plan),
        "arms": metrics,
        "inferential_superiority_claim": False,
        "scientific_truth_certified": False,
        "reviewer_identity_verified_by_evaluator": False,
        "review_evidence_bytes_verified_by_evaluator": False,
        "limits": "Structural validation of operator-supplied registry and evidence references; "
        "independence and evidence authenticity require external due diligence. "
        "Missing results stay in denominators; unknown costs are not zero costs.",
    }


def valid_hash(value):
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("results", type=Path, nargs="?")
    parser.add_argument("reviews", type=Path, nargs="?")
    parser.add_argument("--plan-hash", action="store_true")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text())
        if args.plan_hash:
            print(digest(plan))
            return
        require(
            args.results is not None and args.reviews is not None,
            "Results and reviews paths required",
        )
        report = evaluate(
            plan, json.loads(args.results.read_text()), json.loads(args.reviews.read_text())
        )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"Pilot validation failed: {exc}\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
