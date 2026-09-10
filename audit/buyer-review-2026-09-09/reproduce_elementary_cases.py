"""Read-only audit: fetch JSON as data; run only this reviewer's elementary code."""

import datetime
import hashlib
import json
import math
import pathlib
import platform
import urllib.request
from collections import Counter

BASE = "http://127.0.0.1:8700"
OUT = pathlib.Path(__file__).parent


def fetch(path):
    # BASE is a fixed loopback HTTP origin; callers use local API paths only.
    with urllib.request.urlopen(BASE + path, timeout=15) as response:  # noqa: S310
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("audit response exceeds limit")
    return raw


def get(path):
    return json.loads(fetch(path))


def sieve(limit):
    marked = [True] * limit
    marked[:2] = [False, False]
    for p in range(2, math.isqrt(limit - 1) + 1):
        if marked[p]:
            for multiple in range(p * p, limit, p):
                marked[multiple] = False
    return [n for n in range(2, limit) if marked[n]]


def trial(limit):
    return [n for n in range(2, limit) if all(n % d for d in range(2, math.isqrt(n) + 1))]


result = {
    "captured_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    "runtime": platform.python_version(),
    "scope": "local API; no agent execution or mutation",
    "reviewer_script_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
}
prime_id = "mis_01M1B14JCTKPRG9263VK6R4RPN"
opn_id = "mis_01M180K8WS7CY8R967MG8AZY5W"
for label, mid in [("prime_sieve", prime_id), ("opn", opn_id)]:
    data = get("/v1/mission-challenges/" + mid)
    submissions = data["submissions"]
    result[label] = {
        k: data[k]
        for k in [
            "mission_id",
            "objective",
            "state",
            "participants_count",
            "submissions_count",
            "votes_count",
            "resolved_votes",
            "abstentions_count",
            "winning_submission_id",
            "final_artifact_version_ids",
        ]
    }
    result[label]["submission_completeness"] = {
        "with_artifact_ids": sum(bool(s["artifact_version_ids"]) for s in submissions),
        "with_evidence_ids": sum(bool(s["evidence_ids"]) for s in submissions),
        "with_claim_ids": sum(bool(s["claim_ids"]) for s in submissions),
        "with_experiments": sum(bool(s["experiments"]) for s in submissions),
    }
    result[label]["submissions"] = [
        {
            k: s[k]
            for k in [
                "submission_id",
                "artifact_version_ids",
                "claim_ids",
                "evidence_ids",
                "state",
                "resolved_votes",
            ]
        }
        for s in submissions
    ]
    if label == "prime_sieve":
        artifacts = []
        for s in submissions:
            for aid in s["artifact_version_ids"]:
                meta = get("/v1/artifact-versions/" + aid)
                raw = fetch("/v1/artifact-versions/" + aid + "/download")
                packet = json.loads(raw)
                exp = packet.get("experiments", {})
                artifacts.append(
                    {
                        "artifact_version_id": aid,
                        "submission_id": s["submission_id"],
                        "stored_hash": meta["content_hash"],
                        "download_sha256_matches": hashlib.sha256(raw).hexdigest()
                        == meta["content_hash"],
                        "size_matches": len(raw) == meta["content_size"],
                        "artifact_json_keys": sorted(packet),
                        "experiments": exp,
                        "replication_instructions": packet.get("replication_instructions"),
                        "contains_source_code_field": any(
                            k in packet for k in ["code", "source", "script"]
                        ),
                        "publication_readiness": packet.get("publication_readiness"),
                        "packet_sha256": packet.get("packet_sha256"),
                    }
                )
        result[label]["artifacts"] = artifacts
        result[label]["experiment_hash_frequency"] = dict(
            Counter(a["experiments"].get("prime_list_sha256", "missing") for a in artifacts)
        )
        result[label]["description_reward_discrepancy"] = {
            "description": data["description"],
            "reward_aceros": data["reward_aceros"],
            "completion_policy": data["completion_policy"],
            "top_level_reward_split": data["reward_split"],
        }

computations = {}
for limit in [500, 10000]:
    a, b = sieve(limit), trial(limit)
    assert a == b
    digest = hashlib.sha256(",".join(map(str, a)).encode()).hexdigest()
    altered = [1] + a
    computations[str(limit)] = {
        "range": f"2 <= n < {limit}",
        "prime_count": len(a),
        "first_20": a[:20],
        "last_10": a[-10:],
        "algorithms_agree": True,
        "comma_decimal_sha256": digest,
        "inserting_1_changes_digest": hashlib.sha256(
            ",".join(map(str, altered)).encode()
        ).hexdigest()
        != digest,
    }
for a in result["prime_sieve"]["artifacts"]:
    a["independent_digest_matches"] = (
        a["experiments"].get("prime_list_sha256") == computations["500"]["comma_decimal_sha256"]
    )
result["independent_prime_computations"] = computations
squares = sum(i * i for i in range(1, 101))
closed = 100 * 101 * 201 // 6
mutant = sum(i * i for i in range(1, 100))
assert squares == closed == 338350 and mutant == 328350
p = pathlib.Path(
    "/home/merari-acero/.agora-agents/universidad-codex-test/artifacts/candidate-rcs_01M1ZEY7JSCZQVKB6SV7XZ3NGF.json"
)
raw = p.read_bytes()
package = json.loads(raw)
result["synthetic_square_fixture"] = {
    "candidate": package["candidate"],
    "local_package_sha256": hashlib.sha256(raw).hexdigest(),
    "declared_inputs": package["final_solution"]["payload"]["inputs"],
    "declared_expected": package["final_solution"]["payload"]["expected_output"],
    "independent_iterative": squares,
    "independent_closed_form": closed,
    "endpoint_mutation": mutant,
    "candidate_canonical_hash_recomputed": False,
    "knowledge_root_recomputed": False,
    "reason_not_recomputed": (
        "Package omits full canonical candidate consensus and genealogy bytes."
    ),
}
(OUT / "experiments-evidence.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "prime_sieve": result["prime_sieve"]["submission_completeness"],
            "opn": result["opn"]["submission_completeness"],
            "artifact_count": len(result["prime_sieve"]["artifacts"]),
            "all_download_hashes_match": all(
                a["download_sha256_matches"] for a in result["prime_sieve"]["artifacts"]
            ),
            "all_prime_digests_match": all(
                a["independent_digest_matches"] for a in result["prime_sieve"]["artifacts"]
            ),
            "prime_counts": {k: v["prime_count"] for k, v in computations.items()},
            "square_result": squares,
            "square_mutation": mutant,
        },
        indent=2,
    )
)
