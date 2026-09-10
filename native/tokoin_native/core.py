"""Deterministic native TEST state machine; no DB, clocks, networks or secret keys.

A trusted consensus adapter supplies monotonically increasing block time.
This module does NOT implement consensus or authenticate real institutions.
"""

import copy
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

UNIT = 100_000_000
MAX_SUPPLY = 1_000_000 * UNIT
PILOT_CAP = 500 * UNIT
MATURITY = 365 * 24 * 60 * 60
VERSION = "TOKOIN_NATIVE_REWARD_V2"
MODE = "TEST_NON_RECOGNIZABLE"
SPLIT = {"proposer": 10, "solver": 10, "contributors": 51, "institutions": 20, "infra": 9}
APPROVED = {"APPROVED", "APPROVED_WITH_MINOR_CHANGES"}
VERDICTS = APPROVED | {"REQUIRES_REVISION", "REJECTED", "INSUFFICIENT_EVIDENCE"}


class Invalid(ValueError):
    """Invalid protocol input or state; reject atomically."""


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def integer(value, minimum=0, maximum=MAX_SUPPLY):
    require(type(value) is int and minimum <= value <= maximum, "invalid integer")
    return value


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()), "invalid fields")


def canonical(value):
    visited = 0

    def check(v, depth=0):
        nonlocal visited
        visited += 1
        require(depth <= 48 and visited <= 50000, "canonical structure limits")
        if type(v) is dict:
            require(all(type(k) is str and k.isascii() for k in v), "non-ASCII key")
            for item in v.values():
                check(item, depth + 1)
        elif type(v) is list:
            for item in v:
                check(item, depth + 1)
        else:
            require(v is None or type(v) in (str, int, bool), "unsupported canonical value")
            if type(v) is str:
                require(v.isascii() and len(v) <= 4096, "invalid string")

    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(domain, value):
    return hashlib.sha256(domain.encode() + b"\x00" + canonical(value)).hexdigest()


def hex_value(value, size=64):
    require(
        type(value) is str and re.fullmatch("[0-9a-f]{" + str(size) + "}", value), "invalid hex"
    )
    return value


def identifier(value):
    require(type(value) is str and re.fullmatch("[a-zA-Z0-9_.:-]{1,100}", value), "invalid id")
    return value


def address(public_key):
    hex_value(public_key)
    return "tkn1" + digest("tokoin.address.v1", public_key)


def valid_address(value):
    require(type(value) is str and value.startswith("tkn1"), "invalid address")
    hex_value(value[4:])
    return value


def verify(public_key, domain, payload, signature):
    try:
        hex_value(public_key)
        hex_value(signature, 128)
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), domain.encode() + b"\x00" + canonical(payload)
        )
    except (ValueError, InvalidSignature) as error:
        raise Invalid("invalid signature") from error


def merkle(values):
    level = [bytes.fromhex(digest("tokoin.merkle.leaf.v1", v)) for v in values]
    if not level:
        return digest("tokoin.merkle.empty.v1", [])
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(b"tokoin.merkle.node.v1\x00" + level[i] + level[i + 1]).digest()
            for i in range(0, len(level), 2)
        ]
    return digest("tokoin.merkle.root.v2", {"count": len(values), "root": level[0].hex()})


def split_weighted(total, weights):
    integer(total)
    require(type(weights) is dict and 0 < len(weights) <= 100, "empty/large weights")
    for recipient, weight in weights.items():
        valid_address(recipient)
        integer(weight, 1)
    denominator = sum(weights.values())
    allocations = {k: total * v // denominator for k, v in weights.items()}
    order = sorted(weights, key=lambda k: (-(total * weights[k] % denominator), k))
    for k in order[: total - sum(allocations.values())]:
        allocations[k] += 1
    return allocations


def distribution(total, groups):
    integer(total, 1)
    require(sum(SPLIT.values()) == 100 and set(groups) == set(SPLIT), "invalid distribution")
    # Fixed reward is divisible by 100; reject rather than silently drop pool dust.
    require(total % 100 == 0, "indivisible reward pools")
    result: dict[str, int] = {}
    for name, percent in SPLIT.items():
        for recipient, units in split_weighted(total * percent // 100, groups[name]).items():
            result[recipient] = result.get(recipient, 0) + units
    require(sum(result.values()) == total, "allocation conservation")
    return dict(sorted(result.items()))


def check_capacity(created, amount, pilot=True):
    integer(created)
    integer(amount, 1)
    require(created + amount <= MAX_SUPPLY, "MAX_SUPPLY exceeded")
    if pilot:
        require(created + amount <= PILOT_CAP, "pilot cap exceeded")


def make_genesis(
    chain_id, institutions, infrastructure_address, timestamp, consensus_validators=None
):
    g = {
        "version": VERSION,
        "mode": MODE,
        "chain_id": chain_id,
        "max_supply_units": MAX_SUPPLY,
        "pilot_cap_units": PILOT_CAP,
        "unit": UNIT,
        "maturity_seconds": MATURITY,
        "reward_units": UNIT,
        "distribution": SPLIT.copy(),
        "institutions": institutions,
        "infrastructure_address": infrastructure_address,
        "timestamp": timestamp,
        "consensus_validators": consensus_validators or [],
    }
    initial_state(g)
    return g


def initial_state(genesis):
    fields(
        genesis,
        "version mode chain_id max_supply_units pilot_cap_units unit "
        "maturity_seconds reward_units distribution institutions infrastructure_address timestamp "
        "consensus_validators",
    )
    require(
        genesis["version"] == VERSION and genesis["mode"] == MODE, "unsupported economic genesis"
    )
    identifier(genesis["chain_id"])
    require(genesis["chain_id"].startswith("tokoin-test-"), "TEST chain ID required")
    for k, v in {
        "max_supply_units": MAX_SUPPLY,
        "pilot_cap_units": PILOT_CAP,
        "unit": UNIT,
        "maturity_seconds": MATURITY,
        "reward_units": UNIT,
    }.items():
        require(integer(genesis[k]) == v, "immutable policy mismatch")
    require(genesis["distribution"] == SPLIT, "policy split mismatch")
    valid_address(genesis["infrastructure_address"])
    integer(genesis["timestamp"])
    validators = genesis["consensus_validators"]
    require(type(validators) is list and len(validators) <= 100, "consensus validators")
    for validator in validators:
        fields(validator, "public_key power")
        hex_value(validator["public_key"])
        integer(validator["power"], 1)
    require(len({v["public_key"] for v in validators}) == len(validators), "duplicate block key")
    institutions = genesis["institutions"]
    require(type(institutions) is dict and 2 <= len(institutions) <= 100, "institution count")
    groups = set()
    for key, record in institutions.items():
        hex_value(key)
        fields(record, "institution_id controller_group payout_address label")
        identifier(record["institution_id"])
        identifier(record["controller_group"])
        valid_address(record["payout_address"])
        require(record["label"] == "INSTITUTIONAL_VALIDATOR_TEST", "TEST label required")
        groups.add(record["controller_group"])
    require(len(groups) >= 2, "independent declared controllers required")
    require(
        len({r["institution_id"] for r in institutions.values()}) == len(institutions),
        "duplicate institution",
    )
    return {
        "genesis_hash": digest("tokoin.genesis.v2", genesis),
        "height": 0,
        "time": genesis["timestamp"],
        "created": 0,
        "revoked": 0,
        "balances": {},
        "nonces": {},
        "rewards": {},
        "reviews": {},
        "candidates": {},
        "challenges": {},
    }


def invariant(state):
    integer(state["created"], 0, PILOT_CAP)
    integer(state["revoked"])
    circulating = sum(integer(v) for v in state["balances"].values())
    locked = sum(
        r["authorization"]["reward_total"]
        for r in state["rewards"].values()
        if r["status"] in ("LOCKED", "CHALLENGED")
    )
    require(circulating + locked + state["revoked"] == state["created"], "supply conservation")
    require(state["created"] <= MAX_SUPPLY, "MAX_SUPPLY")


def authorization_hash(body):
    return digest("tokoin.reward.authorization.v2", body)


def review_commitment(reward_hash, verdict, salt):
    hex_value(reward_hash)
    require(verdict in VERDICTS, "invalid verdict")
    hex_value(salt)
    return digest(
        "tokoin.review.commit.v2", {"reward_hash": reward_hash, "verdict": verdict, "salt": salt}
    )


def _reviewers(genesis, keys):
    registry = genesis["institutions"]
    require(len(keys) == 2 and all(k in registry for k in keys), "two registered reviewers")
    require(
        len({registry[k]["controller_group"] for k in keys}) == 2,
        "review controllers not independent",
    )


def _authorization(genesis, state, body):
    fields(
        body,
        "reward_id research_id candidate_version protocol_version genealogy_root "
        "paper_hash dataset_manifest_hash code_manifest_hash reward_total groups distribution_root "
        "participant_controllers",
    )
    identifier(body["reward_id"])
    identifier(body["research_id"])
    integer(body["candidate_version"], 1)
    require(body["protocol_version"] == VERSION, "reward version")
    for k in (
        "genealogy_root",
        "paper_hash",
        "dataset_manifest_hash",
        "code_manifest_hash",
        "distribution_root",
    ):
        hex_value(body[k])
    require(integer(body["reward_total"], 1) == genesis["reward_units"], "fixed TEST reward policy")
    allocations = distribution(body["reward_total"], body["groups"])
    require(
        merkle([[k, v] for k, v in allocations.items()]) == body["distribution_root"],
        "distribution root mismatch",
    )
    require(body["groups"]["infra"] == {genesis["infrastructure_address"]: 1}, "infra destination")
    controllers = body["participant_controllers"]
    require(type(controllers) is list and 0 < len(controllers) <= 100, "participant controllers")
    for controller in controllers:
        identifier(controller)
    reviews = state["reviews"].get(authorization_hash(body), {})
    _reviewers(genesis, list(reviews))
    require(all(r.get("verdict") in APPROVED for r in reviews.values()), "two compatible approvals")
    registry = genesis["institutions"]
    require(
        not set(controllers) & {registry[k]["controller_group"] for k in reviews},
        "declared conflict of interest",
    )
    require(
        set(body["groups"]["institutions"]) == {registry[k]["payout_address"] for k in reviews},
        "institution payout mapping",
    )
    return allocations


def _decision(genesis, payload):
    fields(payload, "decision signatures")
    decision = payload["decision"]
    fields(decision, "chain_id challenge_id reward_id reward_hash outcome")
    require(decision["chain_id"] == genesis["chain_id"], "foreign decision")
    sigs = payload["signatures"]
    require(type(sigs) is dict, "invalid signature set")
    _reviewers(genesis, list(sigs))
    for key, sig in sigs.items():
        verify(key, "tokoin.challenge.decision.v2", decision, sig)
    return decision


def _apply(genesis, s, tx):
    fields(tx, "chain_id kind payload public_key nonce signature")
    require(tx["chain_id"] == genesis["chain_id"], "foreign transaction")
    signer = address(tx["public_key"])
    nonce = integer(tx["nonce"], 1)
    require(nonce == s["nonces"].get(signer, 0) + 1, "nonce/replay")
    unsigned = {k: v for k, v in tx.items() if k != "signature"}
    verify(tx["public_key"], "tokoin.transaction.v2", unsigned, tx["signature"])
    p, kind = tx["payload"], tx["kind"]
    require(type(p) is dict, "payload object required")
    if kind == "review_commit":
        fields(p, "reward_hash commitment")
        hex_value(p["reward_hash"])
        hex_value(p["commitment"])
        key = tx["public_key"]
        require(key in genesis["institutions"], "unregistered reviewer")
        panel = s["reviews"].setdefault(p["reward_hash"], {})
        require(key not in panel and len(panel) < 2, "panel frozen/duplicate")
        prospective = [*panel, key]
        if len(prospective) == 2:
            _reviewers(genesis, prospective)
        panel[key] = {"commitment": p["commitment"]}
    elif kind == "review_reveal":
        fields(p, "reward_hash verdict salt")
        panel = s["reviews"].get(p["reward_hash"], {})
        _reviewers(genesis, list(panel))
        key = tx["public_key"]
        require(key in panel and "verdict" not in panel[key], "missing commit/duplicate reveal")
        require(panel[key]["commitment"] == review_commitment(**p), "reveal mismatch")
        panel[key]["verdict"] = p["verdict"]
        panel[key]["review_hash"] = digest("tokoin.review.v2", p)
    elif kind == "authorize":
        allocations = _authorization(genesis, s, p)
        rid = p["reward_id"]
        candidate = p["research_id"] + ":" + str(p["candidate_version"])
        require(rid not in s["rewards"] and candidate not in s["candidates"], "reward replay")
        require(
            all(
                r["authorization"]["candidate_version"] < p["candidate_version"]
                for r in s["rewards"].values()
                if r["authorization"]["research_id"] == p["research_id"]
            ),
            "candidate version must increase",
        )
        # A research may have only one non-revoked reward across candidate versions.
        require(
            not any(
                r["authorization"]["research_id"] == p["research_id"]
                and r["status"] != "REVOKED_BEFORE_FINALITY"
                for r in s["rewards"].values()
            ),
            "research already rewarded",
        )
        check_capacity(s["created"], p["reward_total"])
        s["created"] += p["reward_total"]
        s["candidates"][candidate] = rid
        s["rewards"][rid] = {
            "authorization": p,
            "allocations": allocations,
            "status": "LOCKED",
            "elapsed": 0,
            "last_started": s["time"],
            "created_at": s["time"],
            "reward_hash": authorization_hash(p),
            "reviews": copy.deepcopy(s["reviews"][authorization_hash(p)]),
        }
    elif kind == "challenge_submit":
        fields(p, "challenge_id reward_id target_claim_hash evidence_hash method_hash")
        identifier(p["challenge_id"])
        require(p["challenge_id"] not in s["challenges"], "duplicate challenge")
        reward = s["rewards"].get(p["reward_id"])
        require(
            reward is not None and reward["status"] in ("LOCKED", "CHALLENGED"),
            "reward not challengeable",
        )
        for key in ("target_claim_hash", "evidence_hash", "method_hash"):
            hex_value(p[key])
        require(
            not any(
                all(c["submission"][k] == p[k] for k in p if k != "challenge_id")
                for c in s["challenges"].values()
            ),
            "duplicate evidence challenge",
        )
        s["challenges"][p["challenge_id"]] = {
            "submission": p,
            "state": "SUBMITTED",
            "challenger": signer,
            "submitted_at": s["time"],
        }
    elif kind == "challenge_decide":
        decision = _decision(genesis, p)
        challenge = s["challenges"].get(decision["challenge_id"])
        require(challenge is not None, "unknown challenge")
        require(challenge["submission"]["reward_id"] == decision["reward_id"], "wrong challenge")
        reward = s["rewards"][decision["reward_id"]]
        require(reward["reward_hash"] == decision["reward_hash"], "wrong candidate")
        outcome = decision["outcome"]
        if outcome == "ADMIT":
            require(
                challenge["state"] == "SUBMITTED" and reward["status"] == "LOCKED",
                "challenge cannot be admitted",
            )
            reward["elapsed"] += s["time"] - reward["last_started"]
            reward["status"] = "CHALLENGED"
            reward["active_challenge"] = decision["challenge_id"]
            challenge["state"] = "ADMITTED"
        elif outcome == "REJECT" and challenge["state"] == "SUBMITTED":
            challenge["state"] = "REJECTED"
        else:
            require(
                challenge["state"] == "ADMITTED"
                and reward["status"] == "CHALLENGED"
                and reward["active_challenge"] == decision["challenge_id"],
                "not active challenge",
            )
            require(outcome in ("REJECT", "MINOR", "MATERIAL", "INVALIDATE"), "invalid outcome")
            challenge["state"] = outcome
            if outcome in ("MATERIAL", "INVALIDATE"):
                reward["status"] = "REVOKED_BEFORE_FINALITY"
                s["revoked"] += reward["authorization"]["reward_total"]
            else:
                reward["status"] = "LOCKED"
                reward["last_started"] = s["time"]
            del reward["active_challenge"]
        challenge.setdefault("decisions", []).append(copy.deepcopy(p))
    elif kind == "finalize":
        fields(p, "reward_id")
        reward = s["rewards"].get(p["reward_id"])
        require(reward is not None and reward["status"] == "LOCKED", "not finalizable")
        require(
            reward["elapsed"] + s["time"] - reward["last_started"] >= MATURITY,
            "365 days not elapsed",
        )
        # Submissions stay in history; only evidence admitted by the scientific
        # protocol suspends finality. A hash-only allegation cannot lock funds.
        for recipient, amount in reward["allocations"].items():
            s["balances"][recipient] = s["balances"].get(recipient, 0) + amount
        reward["status"] = "FINALIZED"
        reward["finalized_at"] = s["time"]
    elif kind == "transfer":
        fields(p, "to amount")
        valid_address(p["to"])
        amount = integer(p["amount"], 1)
        require(s["balances"].get(signer, 0) >= amount, "insufficient transferable balance")
        s["balances"][signer] -= amount
        s["balances"][p["to"]] = s["balances"].get(p["to"], 0) + amount
    else:
        raise Invalid("unsupported transaction")
    s["nonces"][signer] = nonce
    invariant(s)


def transition(genesis, previous, transactions, height, timestamp):
    """Atomic block application. Consensus MUST authenticate height and timestamp."""
    require(previous["genesis_hash"] == digest("tokoin.genesis.v2", genesis), "genesis mismatch")
    require(integer(height, 1) == previous["height"] + 1, "height mismatch")
    require(integer(timestamp) >= previous["time"], "non-monotonic time")
    require(type(transactions) is list and len(transactions) <= 1000, "block size")
    require(len(canonical(transactions)) <= 1_000_000, "block bytes limit")
    s = copy.deepcopy(previous)
    s.update(height=height, time=timestamp)
    for tx in transactions:
        _apply(genesis, s, tx)
    invariant(s)
    return s


def metrics(state):
    locked = sum(
        r["authorization"]["reward_total"]
        for r in state["rewards"].values()
        if r["status"] in ("LOCKED", "CHALLENGED")
    )
    return {
        "chain_height": state["height"],
        "created_units": state["created"],
        "circulating_units": sum(state["balances"].values()),
        "locked_units": locked,
        "revoked_units": state["revoked"],
        "remaining_units": MAX_SUPPLY - state["created"],
        "pilot_remaining_units": PILOT_CAP - state["created"],
        "active_challenges": sum(c["state"] == "ADMITTED" for c in state["challenges"].values()),
        "mode": MODE,
        "genesis_recognition_eligible": False,
    }
