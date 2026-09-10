"""Verified AGORA package -> native application TEST transition campaign.

No node RPC, economic deployment, key files or wall-clock maturity. Explicit
application-time simulation. Separate freshly generated native wallet keys.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native"))


def run_native(
    package: dict, experiment: dict, panel: dict, destination: Path, nodes: list[dict]
) -> dict:
    from agora_api.research_export import verify_package
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from tokoin_native.core import (
        MATURITY,
        TX_VERSION,
        UNIT,
        VERSION,
        Invalid,
        address,
        authorization_hash,
        canonical,
        digest,
        distribution,
        initial_state,
        invariant,
        make_genesis,
        merkle,
        review_commitment,
        transition,
    )
    from tokoin_native.wallet import public_key, sign, transaction

    verify_package(package, package["candidate"]["content_hash"])
    keys = [Ed25519PrivateKey.generate() for _ in range(6)]
    pubs = [public_key(k) for k in keys]
    addresses = [address(p) for p in pubs]
    tracks = panel["tracks"]
    registry = {
        pubs[i]: {
            "institution_id": tracks[i]["validator"]["validator_id"],
            "controller_group": f"TEST-role-controller-{i}",
            "payout_address": addresses[i],
            "label": "INSTITUTIONAL_VALIDATOR_TEST",
        }
        for i in (0, 1)
    }
    genesis = make_genesis(
        "tokoin-test-science-" + experiment["scenario"].lower(), registry, addresses[4], 1000
    )
    state = initial_state(genesis)
    corpus, apphashes, rejected = [], [], []

    def execute(index, kind, payload, timestamp=None):
        nonlocal state
        tx = transaction(
            keys[index], genesis, state["nonces"].get(addresses[index], 0) + 1, kind, payload
        )
        at = state["time"] + 1 if timestamp is None else timestamp
        try:
            result = transition(genesis, state, [tx], state["height"] + 1, at)
        except Invalid as exc:
            rejected.append(
                {"type": kind, "reason": str(exc), "protocol_time": at, "transaction": tx}
            )
            raise
        state = result
        corpus.append({"height": state["height"], "protocol_time": at, "transaction": tx})
        apphashes.append(digest("tokoin.state.v2", state))

    groups = {
        "proposer": {addresses[5]: 1},
        "solver": {addresses[2]: 1},
        "contributors": {addresses[2]: 1, addresses[3]: 1},
        "institutions": {addresses[0]: 1, addresses[1]: 1},
        "infra": {addresses[4]: 1},
    }
    identity_mapping = []
    for index, kind in ((5, "hypothesis"), (2, "experiment_result"), (3, "reproduction_result")):
        node = next(n for n in nodes if n["object_type"] == kind)
        identity_mapping.append(
            {
                "agora_actor_id": node["author_agent_id"],
                "contribution_id": node["object_id"],
                "contribution_hash": node["canonical_content_hash"],
                "native_address": addresses[index],
                "role": kind,
            }
        )
    report = {
        "candidate_hash": package["candidate"]["content_hash"],
        "experiment": experiment,
        "contribution_identity_mapping": identity_mapping,
        "agora_review_hashes": [t["review"]["review_hash"] for t in tracks],
    }
    body = {
        "reward_id": "reward-" + experiment["scenario"],
        "research_id": package["candidate"]["candidate_id"],
        "candidate_version": 1,
        "protocol_version": VERSION,
        "genealogy_root": package["candidate"]["canonical_payload"]["knowledge_root_hash"],
        "paper_hash": digest("agora.alpha.executed-research-report.v1", report),
        "dataset_manifest_hash": digest("agora.alpha.executed-data.v1", experiment["initial"]),
        "code_manifest_hash": experiment["source_worker_sha256"],
        "reward_total": UNIT,
        "groups": groups,
        "distribution_root": merkle([[k, v] for k, v in distribution(UNIT, groups).items()]),
        "participant_controllers": ["TEST-research-controller"],
    }
    reward_hash = authorization_hash(body)
    for i in (0, 1):
        execute(
            i,
            "review_commit",
            {
                "reward_hash": reward_hash,
                "commitment": review_commitment(
                    reward_hash, tracks[i]["review"]["verdict"], str(i) * 64
                ),
            },
        )
    for i in (0, 1):
        execute(
            i,
            "review_reveal",
            {
                "reward_hash": reward_hash,
                "verdict": tracks[i]["review"]["verdict"],
                "salt": str(i) * 64,
            },
        )
    approved = all(t["review"]["verdict"] == "APPROVED" for t in tracks)
    if not approved:
        try:
            execute(2, "authorize", body)
        except Invalid:
            pass
        else:
            raise AssertionError("Negative/inconclusive review minted reward")
        assert state["created"] == 0 and state["rewards"] == {}
    else:
        execute(2, "authorize", body)
        assert state["rewards"][body["reward_id"]]["status"] == "LOCKED"
        try:
            execute(2, "transfer", {"to": addresses[3], "amount": 1})
        except Invalid:
            pass
        else:
            raise AssertionError("Locked reward was spendable")
        if experiment["scenario"] == "SCI-002":
            challenge_id = "challenge-science-002"
            execute(
                3,
                "challenge_submit",
                {
                    "challenge_id": challenge_id,
                    "reward_id": body["reward_id"],
                    "target_claim_hash": body["paper_hash"],
                    "evidence_hash": digest(
                        "agora.alpha.counterexample.v1", experiment["counterexample"]
                    ),
                    "method_hash": body["code_manifest_hash"],
                },
            )

            def decision(outcome):
                d = {
                    "chain_id": genesis["chain_id"],
                    "genesis_hash": state["genesis_hash"],
                    "protocol_version": TX_VERSION,
                    "challenge_revision": 0,
                    "challenge_id": challenge_id,
                    "reward_id": body["reward_id"],
                    "reward_hash": reward_hash,
                    "outcome": outcome,
                }
                return {
                    "decision": d,
                    "signatures": {
                        pubs[i]: sign(keys[i], "tokoin.challenge.decision.v3", d) for i in (0, 1)
                    },
                }

            execute(0, "challenge_decide", decision("ADMIT"))
            try:
                execute(2, "finalize", {"reward_id": body["reward_id"]}, state["time"] + MATURITY)
            except Invalid:
                pass
            else:
                raise AssertionError("Admitted challenge failed to block finality")
            execute(0, "challenge_decide", decision("REJECT"))
        reward = state["rewards"][body["reward_id"]]
        maturity = reward["last_started"] + MATURITY - reward["elapsed"]
        execute(2, "finalize", {"reward_id": body["reward_id"]}, maturity)
        execute(2, "transfer", {"to": addresses[3], "amount": 1})
        assert state["rewards"][body["reward_id"]]["status"] == "FINALIZED"
        assert state["created"] == UNIT
    invariant(state)
    replay = initial_state(genesis)
    for entry in corpus:
        replay = transition(
            genesis, replay, [entry["transaction"]], entry["height"], entry["protocol_time"]
        )
    assert canonical(replay) == canonical(state)
    result = {
        "layer": "NATIVE_APPLICATION_TIME_SIMULATION_NOT_NETWORK_OR_REAL_YEAR",
        "economic_status": "TEST_ONLY_NO_GENESIS_RECOGNITION",
        "same_real_operator": True,
        "controller_groups": "Distinct TEST role fixtures, not independent humans",
        "review_identity_mapping": [
            {
                "agora_actor_id": t["validator"]["actor_id"],
                "agora_review_hash": t["review"]["review_hash"],
                "native_public_key": pubs[i],
            }
            for i, t in enumerate(tracks)
        ],
        "weight_policy": "One executed researcher and one replica; equal TEST work units",
        "challenge_rationale": "Admit then reject: n=9 refutes rival, not accepted count",
        "reward_manifest": body,
        "genesis": genesis,
        "created_units": state["created"],
        "transactions": corpus,
        "apphashes": apphashes,
        "rejected": rejected,
        "final_state": state,
        "replay_equal": True,
        "signed_report_preimage": report,
    }
    destination.joinpath("native-application-e2e.json").write_text(json.dumps(result, indent=2))
    return {
        "approved": approved,
        "created_units": state["created"],
        "replay_equal": True,
        "layer": result["layer"],
        "transaction_count": len(corpus),
    }
