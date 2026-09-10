"""Bounded, deterministic acceptance checks; never execute submitted code."""

import hashlib
import math
from functools import lru_cache
from typing import Any

PRIME_SIEVE_ACCEPTANCE_CONTRACT = {
    "version": "prime-sieve-v1",
    "verifier": "prime_sieve_stdlib_v1",
    "upper_bound_exclusive": 10000,
    "meaning": "bounded_result_consistency_not_execution_attestation",
}
PRIME_SIEVE_GENESIS_OBJECTIVE = (
    "Produce a reproducible public method for listing all primes below 10,000 "
    "and explaining why composite numbers are excluded."
)
PARTIAL_KINDS = {
    "methodology_step",
    "experiment_design",
    "replication_step",
    "negative_result",
    "research_branch",
    "partial_result",
}


@lru_cache(maxsize=8)
def _prime_reference(limit: int) -> tuple[int, str]:
    # Trial division is independent of the advertised Eratosthenes sieve.
    primes = [n for n in range(2, limit) if all(n % d for d in range(2, math.isqrt(n) + 1))]
    digest = hashlib.sha256(",".join(map(str, primes)).encode("ascii")).hexdigest()
    return len(primes), digest


def assess_solution_scope(mission: Any, submission: Any) -> dict[str, Any]:
    experiments = submission.experiments or {}
    if not isinstance(experiments, dict):
        experiments = {}
    kind = experiments.get("contribution_kind")
    if (isinstance(kind, str) and kind in PARTIAL_KINDS) or (
        experiments.get("scope_complete") is False
    ):
        return {
            "status": "partial_contribution",
            "eligible_for_full_resolution": False,
            "blockers": ["partial_contribution_cannot_resolve_full_challenge"],
        }
    problem = mission.challenge_problem or {}
    contract = problem.get("acceptance_contract")
    contract_source = "explicit_challenge_contract"
    if contract is None and getattr(mission, "challenge_kind", None) == "genesis_training":
        known_prime = (
            type(problem.get("genesis_sequence")) is int
            and problem["genesis_sequence"] == 1
            and problem.get("name") == "Prime Sieve Reproducibility"
            and problem.get("status") == "training_problem"
            and getattr(mission, "objective", None) == PRIME_SIEVE_GENESIS_OBJECTIVE
        )
        if known_prime:
            contract = PRIME_SIEVE_ACCEPTANCE_CONTRACT
            contract_source = "legacy_genesis_definition"
        elif problem.get("genesis_sequence") == 1 or (
            problem.get("name") == "Prime Sieve Reproducibility"
        ):
            return {
                "status": "needs_information",
                "eligible_for_full_resolution": False,
                "blockers": ["unrecognized_legacy_prime_definition"],
                "contract_source": "legacy_genesis_definition_unrecognized",
            }
    if contract is None:
        return {
            "status": "legacy_unscoped",
            "eligible_for_full_resolution": True,
            "blockers": [],
            "verified": False,
        }
    if (
        not isinstance(contract, dict)
        or contract.get("version") != "prime-sieve-v1"
        or (contract.get("verifier") != "prime_sieve_stdlib_v1")
    ):
        return {
            "status": "needs_information",
            "eligible_for_full_resolution": False,
            "blockers": ["unsupported_acceptance_contract"],
        }
    limit = contract.get("upper_bound_exclusive")
    if type(limit) is not int or not 3 <= limit <= 100000:
        return {
            "status": "needs_information",
            "eligible_for_full_resolution": False,
            "blockers": ["invalid_or_unbounded_acceptance_contract"],
        }
    blockers = []
    if type(experiments.get("limit")) is not int or experiments["limit"] != limit:
        blockers.append("declared_bound_does_not_match_challenge")
    count, digest = _prime_reference(limit)
    if type(experiments.get("prime_count")) is not int or experiments["prime_count"] != count:
        blockers.append("prime_count_mismatch_or_missing")
    if experiments.get("prime_list_sha256") != digest:
        blockers.append("prime_list_digest_mismatch_or_missing")
    return {
        "status": "needs_information" if blockers else "bounded_result_verified",
        "eligible_for_full_resolution": not blockers,
        "blockers": blockers,
        "contract_version": contract["version"],
        "contract_source": contract_source,
        "verification_scope": "declared_finite_result_not_execution_or_novelty",
        "upper_bound_exclusive": limit,
    }
