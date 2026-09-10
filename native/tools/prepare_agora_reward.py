#!/usr/bin/env python3
"""Offline AGORA -> native TEST authorization draft; never signs or submits."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "native"), str(ROOT / "apps/api")]
from agora_api.research_export import verify_package

from tokoin_native.core import UNIT, VERSION, authorization_hash, distribution, merkle, require


def prepare(package, expected_hash, plan, files):
    checked = verify_package(package, expected_hash)
    candidate = package["candidate"]["canonical_payload"]
    require(
        set(plan) == {"reward_id", "groups", "participant_controllers"}, "invalid allocation plan"
    )
    require(
        set(files) == {"paper", "dataset_manifest", "code_manifest"}, "three actual files required"
    )
    # These files are supplied for review; their association is not automatically certified.
    hashes = {k + "_hash": hashlib.sha256(v.read_bytes()).hexdigest() for k, v in files.items()}
    allocation = distribution(UNIT, plan["groups"])
    body = {
        "reward_id": plan["reward_id"],
        "research_id": candidate["challenge_id"],
        "candidate_version": candidate["candidate_version"],
        "protocol_version": VERSION,
        "genealogy_root": checked["knowledge_root_hash"],
        **hashes,
        "reward_total": UNIT,
        "groups": plan["groups"],
        "participant_controllers": plan["participant_controllers"],
        "distribution_root": merkle([[k, v] for k, v in allocation.items()]),
    }
    return {
        "mode": "TEST_NON_RECOGNIZABLE",
        "status": "DRAFT_REQUIRES_BLIND_REVIEW",
        "source_candidate_hash": expected_hash,
        "source_integrity": checked,
        "artifact_association_review_required": True,
        "authorization": body,
        "authorization_hash": authorization_hash(body),
        "signed": False,
        "submitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--expected-candidate-hash", required=True)
    p.add_argument("--allocation-plan", type=Path, required=True)
    for name in ("paper", "dataset-manifest", "code-manifest", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    draft = prepare(
        json.loads(args.package.read_text()),
        args.expected_candidate_hash,
        json.loads(args.allocation_plan.read_text()),
        {
            "paper": args.paper,
            "dataset_manifest": args.dataset_manifest,
            "code_manifest": args.code_manifest,
        },
    )
    args.output.write_text(json.dumps(draft, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": draft["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
