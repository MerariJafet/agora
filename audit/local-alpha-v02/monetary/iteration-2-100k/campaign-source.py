"""Deterministic multi-transition TEST monetary campaign, never real wallet material."""

import argparse
import copy
import hashlib
import json
import random
import time
from collections import Counter
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tokoin_native.core import (
    MATURITY,
    MAX_SUPPLY,
    PILOT_CAP,
    SPLIT,
    UNIT,
    VERSION,
    Invalid,
    address,
    authorization_hash,
    canonical,
    check_capacity,
    digest,
    distribution,
    initial_state,
    invariant,
    make_genesis,
    merkle,
    review_commitment,
    transition,
)
from tokoin_native.wallet import public_key, transaction


def fixture():
    # Public reproducible TEST-only derivation. Never use these keys for real funds.
    keys = [Ed25519PrivateKey.from_private_bytes(
        hashlib.sha256(f"TOKOIN PUBLIC MONETARY TEST FIXTURE {i}".encode()).digest()
    ) for i in range(5)]
    pubs = [public_key(k) for k in keys]
    addresses = [address(p) for p in pubs]
    registry = {pubs[i]: {"institution_id": f"TEST-{i}", "controller_group": f"owner-{i}",
                        "payout_address": addresses[i], "label": "INSTITUTIONAL_VALIDATOR_TEST"}
                for i in (0, 1)}
    genesis = make_genesis("tokoin-test-monetary-campaign", registry, addresses[4], 1000)
    state = initial_state(genesis)
    groups = {"proposer": {addresses[2]: 1}, "solver": {addresses[2]: 1},
              "contributors": {addresses[2]: 3, addresses[3]: 1},
              "institutions": {addresses[0]: 1, addresses[1]: 1}, "infra": {addresses[4]: 1}}

    def apply(index, kind, payload, timestamp=None):
        nonlocal state
        tx = transaction(keys[index], genesis, state["nonces"].get(addresses[index], 0) + 1,
                         kind, payload)
        state = transition(genesis, state, [tx], state["height"] + 1,
                           timestamp if timestamp is not None else state["time"] + 1)

    bodies = []
    for number in (1, 2):
        body = {"reward_id": f"reward-{number}", "research_id": f"research-{number}",
                "candidate_version": number, "protocol_version": VERSION,
                "genealogy_root": digest("test", ["graph", number]), "paper_hash": "a" * 64,
                "dataset_manifest_hash": "b" * 64, "code_manifest_hash": "c" * 64,
                "reward_total": UNIT, "groups": groups,
                "distribution_root": merkle(
                    [[k, v] for k, v in distribution(UNIT, groups).items()]),
                "participant_controllers": ["researcher-owner"]}
        reward_hash = authorization_hash(body)
        for i in (0, 1):
            apply(i, "review_commit", {"reward_hash": reward_hash,
                  "commitment": review_commitment(reward_hash, "APPROVED", str(i) * 64)})
        for i in (0, 1):
            apply(i, "review_reveal", {"reward_hash": reward_hash,
                                      "verdict": "APPROVED", "salt": str(i) * 64})
        apply(2, "authorize", body)
        if number == 1:
            apply(2, "finalize", {"reward_id": "reward-1"}, state["time"] + MATURITY)
        bodies.append(body)
    return genesis, keys, addresses, state, groups, bodies


def reference_distribution(total, groups):
    """Independent integer largest-remainder reference (no protocol allocation helper)."""
    def divide(amount, weights):
        denominator = sum(weights.values())
        result, residual = {}, []
        for name, weight in weights.items():
            quotient, remainder = divmod(amount * weight, denominator)
            result[name] = quotient
            residual.append((-remainder, name))
        missing = amount - sum(result.values())
        for _, name in sorted(residual)[:missing]:
            result[name] += 1
        return result
    result: Counter[str] = Counter()
    for group, budget in divide(total, SPLIT).items():
        result.update(divide(budget, groups[group]))
    return dict(sorted(result.items()))


def run_campaign(sequences=100000, seed=20260909, progress=None):
    if type(sequences) is not int or sequences < 1:
        raise ValueError("positive sequence count required")
    if not __debug__:
        raise RuntimeError("campaign requires assertions enabled")
    started = time.monotonic()
    rng = random.Random(seed)  # noqa: S311 - deterministic non-secret test corpus
    genesis, keys, addresses, baseline, groups, bodies = fixture()
    corpus = hashlib.sha256()
    counts: Counter[str] = Counter()
    first_failure = None
    for number in range(sequences):
        state = copy.deepcopy(baseline)
        balances = dict(state["balances"])
        nonces = dict(state["nonces"])
        sequence: list[dict] = []
        try:
            def execute(tx, label, reject=False, sequence=sequence,
                        balances=balances, nonces=nonces):
                nonlocal state
                before = canonical(state)
                counts["transition_attempts"] += 1
                sequence.append({"label": label, "transaction": tx, "expect_rejection": reject})
                try:
                    candidate = transition(genesis, state, [tx], state["height"] + 1,
                                           state["time"] + 1)
                except Invalid:
                    if not reject:
                        raise AssertionError("unexpected protocol rejection") from None
                    counts["expected_rejections"] += 1
                    assert canonical(state) == before, "rejection mutated prior state"
                else:
                    assert not reject, "invalid transaction unexpectedly accepted"
                    state = candidate
                    counts["accepted_transitions"] += 1
                counts[label] += 1
                invariant(state)
                assert state["created"] == 2 * UNIT
                assert sum(state["balances"].values()) == UNIT
                assert state["rewards"]["reward-2"]["status"] == "LOCKED"
                assert state["balances"] == balances, "reference balance disagreement"
                assert state["nonces"] == nonces, "reference nonce disagreement"

            # Every generated sequence has four actual state-transition invocations.
            first = None
            for sender, receiver in ((2, 3), (3, 2)):
                amount = rng.randint(1, min(balances[addresses[sender]], UNIT // 10))
                nonce = nonces.get(addresses[sender], 0) + 1
                tx = transaction(keys[sender], genesis, nonce, "transfer",
                                 {"to": addresses[receiver], "amount": amount})
                balances[addresses[sender]] -= amount
                balances[addresses[receiver]] += amount
                nonces[addresses[sender]] = nonce
                execute(tx, "valid_transfer")
                if first is None:
                    first = tx
            variant = number % 4
            if variant == 0:
                execute(first, "replay", True)
            elif variant == 1:
                tx = transaction(keys[2], genesis, nonces[addresses[2]] + rng.randint(2, 999),
                                 "transfer", {"to": addresses[3], "amount": 1})
                execute(tx, "bad_nonce", True)
            elif variant == 2:
                tx = transaction(keys[2], genesis, nonces[addresses[2]] + 1, "transfer",
                                 {"to": addresses[3], "amount": balances[addresses[2]] + 1})
                execute(tx, "cannot_spend_locked_supply", True)
            else:
                tx = transaction(keys[2], genesis, nonces[addresses[2]] + 1,
                                 "authorize", bodies[0])
                execute(tx, "reward_replay", True)
            rid = "reward-2" if number % 2 else "reward-1"
            tx = transaction(keys[2], genesis, nonces[addresses[2]] + 1,
                             "finalize", {"reward_id": rid})
            execute(tx, "premature_finality" if number % 2 else "double_finality", True)

            # Boundary calls are counted separately, never inflated into sequences/transitions.
            for pilot, cap in ((True, PILOT_CAP), (False, MAX_SUPPLY)):
                remaining = rng.randint(1, UNIT)
                check_capacity(cap - remaining, remaining, pilot=pilot)
                counts["capacity_accepts"] += 1
                try:
                    check_capacity(cap - remaining, remaining + 1, pilot=pilot)
                except Invalid:
                    counts["capacity_expected_rejections"] += 1
                else:
                    raise AssertionError("cap plus one accepted")
            total = (1, 17, 99, 100, UNIT, PILOT_CAP, MAX_SUPPLY)[number % 7]
            allocation = distribution(total, groups)
            assert allocation == reference_distribution(total, groups)
            assert sum(allocation.values()) == total
            counts["allocation_reference_checks"] += 1
            corpus.update(canonical({"index": number, "sequence": sequence,
                                     "allocation_total": total}))
            counts["completed_sequences"] += 1
        except Exception as error:
            counts["execution_errors"] += 1
            first_failure = {"index": number, "error_type": type(error).__name__,
                             "message": str(error), "sequence": sequence}
            break
        if progress and (number + 1) % 10000 == 0:
            progress(number + 1)
    counts.setdefault("execution_errors", 0)
    return {"mode": "TEST_NON_RECOGNIZABLE", "seed": seed, "requested_sequences": sequences,
            "counts": dict(counts), "corpus_sha256": corpus.hexdigest(),
            "first_failure": first_failure, "elapsed_seconds": round(time.monotonic() - started, 3),
            "pass": first_failure is None and counts["completed_sequences"] == sequences,
            "sequence_definition": "2 accepted signed transfers + 2 rejected signed transitions",
            "source_hashes": {str(p.relative_to(Path(__file__).resolve().parents[2])):
                              hashlib.sha256(p.read_bytes()).hexdigest() for p in
                              (Path(__file__).resolve(),
                               Path(__file__).resolve().parents[1] / "tokoin_native/core.py",
                               Path(__file__).resolve().parents[1] / "tokoin_native/wallet.py")}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequences", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=20260909)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = run_campaign(args.sequences, args.seed,
                          lambda count: print(f"completed_sequences={count}", flush=True))
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"pass": result["pass"], "counts": result["counts"],
                      "corpus_sha256": result["corpus_sha256"]}), flush=True)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
