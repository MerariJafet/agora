"""Versioned deterministic scientific provenance and verdict-neutral review settlement."""

import copy

from .core import (
    MATURITY,
    SPLIT,
    UNIT,
    Invalid,
    address,
    canonical,
    check_capacity,
    digest,
    fields,
    hex_value,
    identifier,
    initial_state,
    merkle,
    require,
    split_weighted,
    verify,
)
from .protocol_time import ProtocolTime

PROTOCOL = "AGORA_NATIVE_SCIENCE_V03"
KINDS = {
    "challenge_created",
    "hypothesis_registered",
    "agent_contribution_registered",
    "evidence_committed",
    "experiment_registered",
    "experiment_result_committed",
    "replication_registered",
}
VERDICTS = {"APPROVE", "REJECT", "INCONCLUSIVE", "REQUEST_REPLICATION"}
RECEIPT_FIELDS = (
    "review_id challenge_id reviewer_identity institution_identity_if_applicable "
    "methodology_assessment evidence_assessment replication_assessment verdict "
    "conflict_of_interest_declaration protocol_version contribution_tree_root evidence_refs"
)


def genesis_v03(base, identity_commitments):
    result = copy.deepcopy(base)
    result["scientific_protocol"] = PROTOCOL
    result["science_identity_commitments"] = copy.deepcopy(identity_commitments)
    initial_v03(result)
    return result


def initial_v03(genesis):
    require(genesis["scientific_protocol"] == PROTOCOL, "unsupported science protocol")
    commitments = genesis.get("science_identity_commitments")
    require(
        type(commitments) is dict and 2 <= len(commitments) <= 100,
        "closed pilot identity registry required",
    )
    for key, value in commitments.items():
        hex_value(key)
        hex_value(value)
    require(
        set(genesis["institutions"]) <= set(commitments), "reviewer identity commitment missing"
    )
    base = {
        k: v
        for k, v in genesis.items()
        if k not in {"scientific_protocol", "science_identity_commitments"}
    }
    state = initial_state(base)
    state["genesis_hash"] = digest("tokoin.genesis.v2", genesis)
    state["science"] = {
        "identities": {},
        "agent_keys": {},
        "events": {},
        "research": {},
        "receipts": {},
    }
    return state


def tree(state, challenge_id):
    ids = state["science"]["research"][challenge_id]["events"]
    return merkle([[eid, state["science"]["events"][eid]["content_hash"]] for eid in sorted(ids)])


def commitment(body, salt):
    hex_value(salt)
    return digest("tokoin.reviewreceipt.commit.v03", {"body": body, "salt": salt})


def receipt(key, body, salt):
    """Pure representation except caller-supplied signing key; no I/O or randomness."""
    from .wallet import sign

    result = dict(
        body,
        commit_hash=commitment(body, salt),
        reveal_hash=digest("tokoin.reviewreceipt.reveal.v03", body),
    )
    return dict(result, signature=sign(key, "tokoin.reviewreceipt.v03", result))


def _identity(s, tx):
    key = tx["public_key"]
    require(key in s["science"]["identities"], "science identity required")
    return s["science"]["identities"][key]


def _research(s, cid):
    identifier(cid)
    require(cid in s["science"]["research"], "unknown research challenge")
    return s["science"]["research"][cid]


def _panel(g, s, r):
    panel = r["reviews"]
    require(len(panel) == 2, "two committed reviewers required")
    require(
        len({g["institutions"][key]["controller_group"] for key in panel}) == 2,
        "distinct declared reviewer controllers required",
    )
    return panel


def _fund(g, s, r, rid, total, allocations, kind):
    require(rid not in s["rewards"], "reward replay")
    require(sum(allocations.values()) == total, "reward conservation")
    check_capacity(s["created"], total)
    auth = {
        "reward_id": rid,
        "research_id": r["challenge_id"],
        "challenge_id": r["challenge_id"],
        "candidate_version": 1,
        "protocol_version": PROTOCOL,
        "genealogy_root": r["tree_root"],
        "contribution_tree_root": r["tree_root"],
        "reward_total": total,
        "distribution_root": merkle([[k, v] for k, v in sorted(allocations.items())]),
        "nominal_budget_units": UNIT,
        "pool_kind": kind,
        "review_receipt_hashes": r["receipt_hashes"],
    }
    s["rewards"][rid] = {
        "authorization": auth,
        "allocations": dict(sorted(allocations.items())),
        "status": "LOCKED",
        "elapsed": 0,
        "last_started": s["time"],
        "created_at": s["time"],
        "unlock_at": ProtocolTime(s["time"]).deadline(MATURITY),
        "reward_hash": digest("tokoin.science.reward.v03", auth),
        "reviews": copy.deepcopy(r["reviews"]),
    }
    s["created"] += total


def apply(g, s, tx):
    require(g.get("scientific_protocol") == PROTOCOL, "science genesis required")
    p, k, key = tx["payload"], tx["kind"], tx["public_key"]
    science = s["science"]
    if k == "science_identity":
        fields(p, "agent_id model provider passport_hash controller_group")
        for name in ("agent_id", "model", "provider", "controller_group"):
            identifier(p[name])
        hex_value(p["passport_hash"])
        require(
            g["science_identity_commitments"].get(key) == digest("tokoin.science.identity.v03", p),
            "identity immutable: differs from genesis commitment",
        )
        require(
            key not in science["identities"] and p["agent_id"] not in science["agent_keys"],
            "identity immutable/duplicate",
        )
        require(len(science["identities"]) < 100, "identity bound")
        science["identities"][key] = copy.deepcopy(p)
        science["agent_keys"][p["agent_id"]] = key
        return
    identity = _identity(s, tx)
    if k == "science_event":
        fields(p, "event_id challenge_id kind agent_id parents content content_hash")
        identifier(p["event_id"])
        identifier(p["challenge_id"])
        require(p["event_id"] not in science["events"], "duplicate scientific event")
        require(p["agent_id"] == identity["agent_id"], "scientific author mismatch")
        require(type(p["kind"]) is str and p["kind"] in KINDS, "scientific event type")
        require(type(p["content"]) is dict, "scientific content object")
        require(
            p["content_hash"] == digest("tokoin.science.content.v03", p["content"]),
            "scientific content hash",
        )
        require(type(p["parents"]) is list and len(p["parents"]) <= 30, "parent bound")
        require(all(type(e) is str for e in p["parents"]), "parent identity required")
        require(len(set(p["parents"])) == len(p["parents"]), "duplicate parent")
        if p["kind"] == "challenge_created":
            require(
                p["challenge_id"] not in science["research"] and not p["parents"],
                "challenge replay/parents",
            )
            r = {
                "challenge_id": p["challenge_id"],
                "proposer_key": key,
                "events": [],
                "reviews": {},
                "objections": {},
                "status": "OPEN",
            }
            science["research"][p["challenge_id"]] = r
        else:
            r = _research(s, p["challenge_id"])
            require(
                r["status"] == "OPEN" and not r["reviews"], "contribution tree locked for review"
            )
            require(bool(p["parents"]), "parent required")
            require(all(e in r["events"] for e in p["parents"]), "foreign/missing parent")
            ancestors, pending = set(), list(p["parents"])
            while pending:
                eid = pending.pop()
                if eid not in ancestors:
                    ancestors.add(eid)
                    pending.extend(science["events"][eid]["parents"])
            prerequisites = {
                "hypothesis_registered": "challenge_created",
                "agent_contribution_registered": "hypothesis_registered",
                "evidence_committed": "agent_contribution_registered",
                "experiment_registered": "evidence_committed",
                "experiment_result_committed": "experiment_registered",
                "replication_registered": "experiment_result_committed",
            }
            require(
                prerequisites[p["kind"]] in {science["events"][e]["kind"] for e in ancestors},
                "scientific stage predecessor required",
            )
        require(len(r["events"]) < 100, "research event bound")
        science["events"][p["event_id"]] = copy.deepcopy(p) | {
            "public_key": key,
            "height": s["height"],
            "protocol_time": s["time"],
        }
        r["events"].append(p["event_id"])
        return
    r = _research(s, p.get("challenge_id"))
    if k == "science_review_commit":
        fields(p, "challenge_id commitment")
        require(key in g["institutions"], "registered epistemic reviewer required")
        require(r["status"] == "OPEN", "review state")
        require(
            key not in r["reviews"] and len(r["reviews"]) < 2, "review commit replay/panel full"
        )
        authors = {science["events"][eid]["public_key"] for eid in r["events"]}
        require(key not in authors, "self review prohibited")
        author_groups = {science["identities"][a]["controller_group"] for a in authors}
        require(
            not {identity["controller_group"], g["institutions"][key]["controller_group"]}
            & author_groups,
            "declared or registered owner conflict",
        )
        require(
            {science["events"][eid]["kind"] for eid in r["events"]} >= KINDS,
            "incomplete scientific lifecycle",
        )
        hex_value(p["commitment"])
        r["reviews"][key] = {"commitment": p["commitment"]}
        r["tree_root"] = tree(s, p["challenge_id"])
        if len(r["reviews"]) == 2:
            _panel(g, s, r)
    elif k == "science_review_reveal":
        fields(p, "challenge_id receipt salt")
        panel = _panel(g, s, r)
        require(key in panel and "receipt" not in panel[key], "review reveal replay/missing commit")
        value = p["receipt"]
        fields(value, RECEIPT_FIELDS + " commit_hash reveal_hash signature")
        body = {name: value[name] for name in RECEIPT_FIELDS.split()}
        require(body["challenge_id"] == p["challenge_id"], "receipt challenge binding")
        require(body["reviewer_identity"] == identity["agent_id"], "receipt reviewer binding")
        require(
            body["institution_identity_if_applicable"] == g["institutions"][key]["institution_id"],
            "receipt institution binding",
        )
        identifier(body["review_id"])
        require(body["review_id"] not in science["receipts"], "duplicate review receipt")
        require(body["protocol_version"] == PROTOCOL, "receipt version")
        require(type(body["verdict"]) is str and body["verdict"] in VERDICTS, "receipt verdict")
        require(
            body["conflict_of_interest_declaration"] == {"has_conflict": False}, "review conflict"
        )
        require(body["contribution_tree_root"] == r["tree_root"], "receipt tree binding")
        refs = body["evidence_refs"]
        require(type(refs) is list and len(refs) >= 3 and len(refs) <= 100, "review evidence refs")
        require(all(type(e) is str and e in r["events"] for e in refs), "foreign review evidence")
        require(
            {science["events"][e]["kind"] for e in refs}
            >= {"experiment_registered", "experiment_result_committed", "replication_registered"},
            "review must reference method/result/replication",
        )
        for name in ("methodology_assessment", "evidence_assessment", "replication_assessment"):
            require(
                type(body[name]) is str and 1 <= len(body[name]) <= 4096,
                "review assessment required",
            )
        expected = commitment(body, p["salt"])
        require(
            value["commit_hash"] == panel[key]["commitment"] == expected,
            "review commitment mismatch",
        )
        require(
            value["reveal_hash"] == digest("tokoin.reviewreceipt.reveal.v03", body),
            "review reveal hash",
        )
        unsigned = {name: v for name, v in value.items() if name != "signature"}
        verify(key, "tokoin.reviewreceipt.v03", unsigned, value["signature"])
        panel[key]["receipt"] = copy.deepcopy(value)
        science["receipts"][body["review_id"]] = digest("tokoin.reviewreceipt.full.v03", value)
    elif k == "science_decide":
        fields(p, "challenge_id")
        require(r["status"] == "OPEN", "decision replay")
        panel = _panel(g, s, r)
        require(all("receipt" in review for review in panel.values()), "missing review reveal")
        verdicts = [review["receipt"]["verdict"] for review in panel.values()]
        r["decision"] = (
            "APPROVE"
            if all(v == "APPROVE" for v in verdicts)
            else ("REJECT" if "REJECT" in verdicts else "INCONCLUSIVE")
        )
        r["receipt_hashes"] = sorted(
            science["receipts"][v["receipt"]["review_id"]] for v in panel.values()
        )
        r["status"] = "DECIDED"
    elif k == "science_objection":
        fields(p, "challenge_id objection_id target_event_id evidence_hash method_hash")
        require(r["status"] == "DECIDED", "objection window closed")
        identifier(p["objection_id"])
        hex_value(p["evidence_hash"])
        hex_value(p["method_hash"])
        identifier(p["target_event_id"])
        require(p["target_event_id"] in r["events"], "objection claim binding")
        require(
            p["objection_id"] not in r["objections"] and len(r["objections"]) < 10,
            "objection limit/replay",
        )
        require(
            all(
                o["submission"]["evidence_hash"] != p["evidence_hash"]
                for o in r["objections"].values()
            ),
            "duplicate objection evidence",
        )
        r["objections"][p["objection_id"]] = {
            "submission": copy.deepcopy(p),
            "state": "OPEN",
            "author": key,
        }
    elif k == "science_resolve":
        fields(p, "challenge_id decision signatures")
        d = p["decision"]
        fields(d, "chain_id genesis_hash challenge_id objection_id outcome evidence_hash")
        require(
            d["chain_id"] == g["chain_id"] and d["genesis_hash"] == s["genesis_hash"],
            "resolution network binding",
        )
        require(d["challenge_id"] == p["challenge_id"], "resolution challenge binding")
        identifier(d["objection_id"])
        require(d["objection_id"] in r["objections"], "unknown objection")
        obj = r["objections"][d["objection_id"]]
        require(obj["state"] == "OPEN", "resolution replay")
        require(
            d["evidence_hash"] == obj["submission"]["evidence_hash"], "resolution evidence binding"
        )
        require(
            type(d["outcome"]) is str and d["outcome"] in {"DISMISSED", "UPHELD"},
            "resolution outcome",
        )
        require(
            type(p["signatures"]) is dict and set(p["signatures"]) == set(_panel(g, s, r)),
            "two panel signatures required",
        )
        for reviewer, sig in p["signatures"].items():
            verify(reviewer, "tokoin.science.resolve.v03", d, sig)
        obj["state"] = d["outcome"]
        obj["resolution"] = copy.deepcopy(p)
        if d["outcome"] == "UPHELD":
            r["decision"] = "REJECT"
    elif k == "science_freeze":
        fields(p, "challenge_id contribution_tree_root")
        require(r["status"] == "DECIDED", "freeze state")
        require(all(o["state"] != "OPEN" for o in r["objections"].values()), "unresolved objection")
        require(
            p["contribution_tree_root"] == tree(s, p["challenge_id"]) == r["tree_root"],
            "tree mismatch",
        )
        r["status"] = "FROZEN"
    elif k == "science_settle_review":
        fields(p, "challenge_id reward_id")
        require(
            r["status"] == "FROZEN" and "review_reward_id" not in r,
            "review settlement replay/state",
        )
        identifier(p["reward_id"])
        panel = _panel(g, s, r)
        require(all("receipt" in v for v in panel.values()), "qualifying receipts required")
        amount = UNIT * SPLIT["institutions"] // 100
        weights = {g["institutions"][key]["payout_address"]: 1 for key in panel}
        require(len(weights) == 2, "distinct reviewer destinations required")
        allocations = split_weighted(amount, weights)
        _fund(g, s, r, p["reward_id"], amount, allocations, "REVIEW_20")
        r["review_reward_id"] = p["reward_id"]
    elif k == "science_settle_result":
        fields(p, "challenge_id reward_id solver_event_id")
        require(
            r["status"] == "FROZEN" and r.get("decision") == "APPROVE",
            "supported positive result required",
        )
        require(
            "review_reward_id" in r and "result_reward_id" not in r,
            "result settlement replay/order",
        )
        require(
            s["rewards"][r["review_reward_id"]]["status"] in {"LOCKED", "FINALIZED"},
            "review work challenged or revoked",
        )
        require(
            s["rewards"][r["review_reward_id"]].get("scientific_status")
            != "INVALIDATED_AFTER_MATURITY",
            "review scientifically invalidated",
        )
        identifier(p["reward_id"])
        identifier(p["solver_event_id"])
        require(p["solver_event_id"] in r["events"], "solver event required")
        solver = science["events"][p["solver_event_id"]]
        require(solver["kind"] == "experiment_result_committed", "solver must materialize result")
        weights = {}
        for eid in r["events"]:
            node = science["events"][eid]
            if node["kind"] in {
                "agent_contribution_registered",
                "experiment_result_committed",
                "replication_registered",
            }:
                a = address(node["public_key"])
                weights[a] = 1
        allocations = {}
        groups = {
            "proposer": {address(r["proposer_key"]): 1},
            "solver": {address(solver["public_key"]): 1},
            "contributors": weights,
            "infra": {g["infrastructure_address"]: 1},
        }
        for group, shares in groups.items():
            for who, units in split_weighted(UNIT * SPLIT[group] // 100, shares).items():
                allocations[who] = allocations.get(who, 0) + units
        _fund(g, s, r, p["reward_id"], UNIT * 80 // 100, allocations, "RESULT_80")
        r["result_reward_id"] = p["reward_id"]
        s["rewards"][p["reward_id"]]["prerequisite_review_id"] = r["review_reward_id"]
    else:
        raise Invalid("unsupported scientific transaction")
    canonical(science)


def propagate_review_dependency(s, review_id):
    """Pause dependent maturity; preserve already-finalized ownership.

    Overlapping direct and prerequisite challenges conservatively add delay.
    They never shorten either challenge period.
    """
    review = s["rewards"][review_id]
    for reward in s["rewards"].values():
        if reward.get("prerequisite_review_id") != review_id or reward["status"] in {
            "FINALIZED",
            "REVOKED_BEFORE_FINALITY",
        }:
            continue
        invalid = (
            review["status"] == "REVOKED_BEFORE_FINALITY"
            or review.get("scientific_status") == "INVALIDATED_AFTER_MATURITY"
        )
        if invalid:
            reward["status"] = "REVOKED_BEFORE_FINALITY"
            s["revoked"] += reward["authorization"]["reward_total"]
        elif review["status"] == "CHALLENGED":
            reward.setdefault("dependency_paused_at", s["time"])
        elif "dependency_paused_at" in reward:
            reward["dependency_delay"] = (
                reward.get("dependency_delay", 0) + s["time"] - reward.pop("dependency_paused_at")
            )


def validate_dependency_finality(s, reward):
    if "prerequisite_review_id" not in reward:
        return
    review = s["rewards"][reward["prerequisite_review_id"]]
    require(
        review["status"] in {"LOCKED", "FINALIZED"}
        and review.get("scientific_status") != "INVALIDATED_AFTER_MATURITY",
        "review prerequisite challenged or invalid",
    )
    require("dependency_paused_at" not in reward, "review prerequisite paused")
    require(
        s["time"]
        >= max(review["unlock_at"], reward["unlock_at"] + reward.get("dependency_delay", 0)),
        "review prerequisite maturity not elapsed",
    )
