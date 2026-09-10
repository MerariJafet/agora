"""Verify and enrich completed scientific evidence for native-network transport."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from scripts.v03_llm_campaign import hash_object, write_json
from scripts.v03_llm_evaluate import evaluate, verify_tools


def decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def export(directory):
    report = json.loads((directory / "results.json").read_text())
    if report["status"] != "PASS":
        raise ValueError("cannot promote an incomplete scientific API campaign")
    events = json.loads((directory / "api-protocol-events.json").read_text())
    llm = json.loads((directory / "llm/campaign.json").read_text())
    replay_count = verify_tools(llm)
    profiles = {
        e["response"]["actor_id"]: e["response"]
        for e in events
        if e.get("path") == "/v1/research-protocol/institutional-validators"
    }
    cases = {}
    for case_id, case in report["cases"].items():
        creation = next(
            e
            for e in events
            if e.get("path") == "/v1/research-protocol/test-challenges"
            and e.get("request", {}).get("experiment_id") == case_id
        )
        if creation["response"]["mission_id"] != case["challenge_id"]:
            raise ValueError("challenge creation provenance mismatch")
        commits, reveals = [], []
        for review in case["reviews"]:
            profile = profiles[review["agora_agent_id"]]
            expected_body = {
                "assignment_id": review["assignment_id"],
                "validator_id": profile["validator_id"],
                "candidate_id": case["candidate"]["candidate_id"],
                "candidate_content_hash": case["candidate"]["content_hash"],
                "candidate_version": case["package"]["candidate"]["canonical_payload"][
                    "candidate_version"
                ],
                "review": review["payload"],
            }
            expected = hash_object(
                {"domain": "agora.institutional.validator.review.v1", "payload": expected_body}
            )
            if expected != review["commit_hash"]:
                raise ValueError("review commitment reconstruction failed")
            Ed25519PublicKey.from_public_bytes(decode(profile["public_key"])).verify(
                decode(review["signature"]), expected.encode()
            )
            commit_path = (
                f"/v1/research-protocol/pilot-assignments/{review['assignment_id']}/commit"
            )
            reveal_path = (
                f"/v1/research-protocol/pilot-assignments/{review['assignment_id']}/reveal"
            )
            commit_index = next(i for i, e in enumerate(events) if e.get("path") == commit_path)
            reveal_index = next(i for i, e in enumerate(events) if e.get("path") == reveal_path)
            commits.append(commit_index)
            reveals.append(reveal_index)
            review["validator_id"] = profile["validator_id"]
            review["institution_profile"] = profile
            review["conflict_of_interest_declaration"] = events[commit_index]["request"][
                "conflict_declaration"
            ]
            review["public_signature_verified"] = True
        if len(commits) != 2 or max(commits) >= min(reveals):
            raise ValueError("blind commit/reveal ordering violated")
        case["creation"] = creation["response"]
        case["blind_commit_reveal_verified"] = True
        cases[case_id] = case
        write_json(directory / f"{case_id}-verified-network-handoff.json", case)
    result = {
        "schema": "AGORA_V03_NATIVE_SCIENCE_HANDOFF_V1",
        "run_id": report["run_id"],
        "source_commit": report["source_commit"],
        "identities": report["identities"],
        "cases": cases,
        "public_llm_outputs": llm["agents"],
        "api_protocol_events": events,
        "calculator_replays_verified": replay_count,
        "oracle": evaluate(llm),
        "limitations": report["limitations"],
        "native_transport_keys": (
            "Generated and bound separately; no model funds private key exported."
        ),
    }
    result["content_hash"] = hash_object(result)
    write_json(directory / "native-science-handoff.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    value = export(args.directory)
    print(
        json.dumps(
            {
                "cases": len(value["cases"]),
                "calculator_replays": value["calculator_replays_verified"],
                "content_hash": value["content_hash"],
            }
        )
    )
