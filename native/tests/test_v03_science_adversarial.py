"""Independent V0.3 adversarial review; all actions use signed protocol transactions."""

import copy

import pytest
from test_v03_science import ScienceWorld

from tokoin_native.core import (
    MATURITY,
    TX_VERSION,
    UNIT,
    Invalid,
    canonical,
    digest,
    initial_state,
    transition,
)
from tokoin_native.v03_science import commitment, receipt
from tokoin_native.wallet import sign


def replay_prefix(w, records):
    w.state = initial_state(w.genesis)
    w.corpus = []
    for record in records:
        w.state = transition(w.genesis, w.state, [record["tx"]], record["height"], record["time"])
        w.corpus.append(record)


def reviewer_decision(w, reward_id, outcome):
    value = {
        "chain_id": w.genesis["chain_id"],
        "genesis_hash": w.state["genesis_hash"],
        "protocol_version": TX_VERSION,
        "challenge_id": "attack-1",
        "challenge_revision": 0,
        "reward_id": reward_id,
        "reward_hash": w.state["rewards"][reward_id]["reward_hash"],
        "outcome": outcome,
    }
    return {
        "decision": value,
        "signatures": {
            w.pubs[i]: sign(w.keys[i], "tokoin.challenge.decision.v3", value) for i in (0, 1)
        },
    }


def challenge_review(w, outcome=None):
    w.run(
        3,
        "challenge_submit",
        {
            "challenge_id": "attack-1",
            "reward_id": "review-20",
            "target_claim_hash": w.state["science"]["events"]["event-5"]["content_hash"],
            "evidence_hash": "e" * 64,
            "method_hash": "f" * 64,
        },
    )
    w.run(2, "challenge_decide", reviewer_decision(w, "review-20", "ADMIT"))
    if outcome:
        w.run(2, "challenge_decide", reviewer_decision(w, "review-20", outcome))


def settle_both(w):
    w.reviewed()
    w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "review-20"})
    w.run(
        2,
        "science_settle_result",
        {
            "challenge_id": "science-1",
            "reward_id": "result-80",
            "solver_event_id": "event-5",
        },
    )


@pytest.mark.parametrize("verdict", ["REJECT", "INCONCLUSIVE", "REQUEST_REPLICATION"])
def test_mixed_positive_and_nonpositive_review_never_earns_result_pool(verdict):
    w = ScienceWorld()
    prefix = list(w.corpus)
    w.reviewed()
    bodies = copy.deepcopy(w.bodies)
    bodies[1]["verdict"] = verdict
    replay_prefix(w, prefix)
    for i in (0, 1):
        w.run(
            i,
            "science_review_commit",
            {
                "challenge_id": "science-1",
                "commitment": commitment(bodies[i], str(i) * 64),
            },
        )
    for i in (0, 1):
        w.run(
            i,
            "science_review_reveal",
            {
                "challenge_id": "science-1",
                "receipt": receipt(w.keys[i], bodies[i], str(i) * 64),
                "salt": str(i) * 64,
            },
        )
    w.run(2, "science_decide", {"challenge_id": "science-1"})
    w.run(
        2,
        "science_freeze",
        {
            "challenge_id": "science-1",
            "contribution_tree_root": bodies[0]["contribution_tree_root"],
        },
    )
    w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "review-20"})
    assert w.state["created"] == UNIT // 5
    with pytest.raises(Invalid):
        w.run(
            2,
            "science_settle_result",
            {
                "challenge_id": "science-1",
                "reward_id": "result-80",
                "solver_event_id": "event-5",
            },
        )
    assert w.state["created"] == UNIT // 5


def test_registered_owner_cannot_evade_conflict_by_declaring_another_group():
    w = ScienceWorld()
    source = list(w.corpus)
    identity = copy.deepcopy(source[2]["tx"]["payload"])
    identity["controller_group"] = w.genesis["institutions"][w.pubs[0]]["controller_group"]
    w.genesis["science_identity_commitments"][w.pubs[2]] = digest(
        "tokoin.science.identity.v03", identity
    )
    w.state, w.corpus = initial_state(w.genesis), []
    for record in source:
        tx = record["tx"]
        i = w.pubs.index(tx["public_key"])
        payload = copy.deepcopy(tx["payload"])
        if tx["kind"] == "science_identity" and i == 2:
            # Author honestly declares owner-0, which also controls registered reviewer 0.
            payload["controller_group"] = w.genesis["institutions"][w.pubs[0]]["controller_group"]
        w.run(i, tx["kind"], payload)
    with pytest.raises(Invalid, match="conflict|controller|owner"):
        w.run(0, "science_review_commit", {"challenge_id": "science-1", "commitment": "a" * 64})


@pytest.mark.parametrize("resolution", [None, "INVALIDATE", "MATERIAL"])
def test_result_cannot_finalize_after_review_prerequisite_challenged_or_revoked(resolution):
    w = ScienceWorld()
    settle_both(w)
    challenge_review(w, resolution)
    before = canonical(w.state["balances"])
    with pytest.raises(Invalid):
        w.run(2, "finalize", {"reward_id": "result-80"}, w.state["time"] + MATURITY)
    assert canonical(w.state["balances"]) == before


def test_unresolved_scientific_objection_prevents_freeze_and_compensation():
    w = ScienceWorld()
    w.reviewed()
    replay_prefix(w, list(w.corpus[:-1]))  # Valid signed prefix ends at DECIDED.
    w.run(
        3,
        "science_objection",
        {
            "challenge_id": "science-1",
            "objection_id": "objection-1",
            "target_event_id": "event-5",
            "evidence_hash": "e" * 64,
            "method_hash": "f" * 64,
        },
    )
    before = canonical(w.state)
    with pytest.raises(Invalid, match="unresolved"):
        w.run(
            2,
            "science_freeze",
            {
                "challenge_id": "science-1",
                "contribution_tree_root": w.bodies[0]["contribution_tree_root"],
            },
        )
    with pytest.raises(Invalid):
        w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "review-20"})
    assert canonical(w.state) == before


def test_source_hash_tampering_rejected_without_partial_state():
    w = ScienceWorld()
    before = canonical(w.state)
    with pytest.raises(Invalid, match="content hash"):
        w.run(
            2,
            "science_event",
            {
                "event_id": "tampered",
                "challenge_id": "science-1",
                "kind": "evidence_committed",
                "agent_id": "agent-2",
                "parents": ["event-0"],
                "content": {"source": "changed"},
                "content_hash": digest("tokoin.science.content.v03", {"source": "original"}),
            },
        )
    assert canonical(w.state) == before


def test_contributor_cannot_change_author_identity():
    w = ScienceWorld()
    with pytest.raises(Invalid, match="author mismatch"):
        w.run(
            2,
            "science_event",
            {
                "event_id": "impersonate",
                "challenge_id": "science-1",
                "kind": "evidence_committed",
                "agent_id": "agent-3",
                "parents": ["event-0"],
                "content": {},
                "content_hash": digest("tokoin.science.content.v03", {}),
            },
        )


def test_single_commit_freezes_contributions_before_reveal():
    w = ScienceWorld()
    w.run(0, "science_review_commit", {"challenge_id": "science-1", "commitment": "a" * 64})
    with pytest.raises(Invalid, match="locked"):
        w.run(
            2,
            "science_event",
            {
                "event_id": "late",
                "challenge_id": "science-1",
                "kind": "evidence_committed",
                "agent_id": "agent-2",
                "parents": ["event-0"],
                "content": {},
                "content_hash": digest("tokoin.science.content.v03", {}),
            },
        )


def test_no_double_settlement_with_fresh_nonce_and_different_reward_id():
    w = ScienceWorld()
    settle_both(w)
    before = canonical(w.state)
    for kind in ("science_settle_review", "science_settle_result"):
        payload = {"challenge_id": "science-1", "reward_id": "different"}
        if kind.endswith("result"):
            payload["solver_event_id"] = "event-5"
        with pytest.raises(Invalid):
            w.run(2, kind, payload)
    assert canonical(w.state) == before and w.state["created"] == UNIT


def test_replication_cannot_precede_any_experiment_result():
    w = ScienceWorld()
    replay_prefix(w, list(w.corpus[:6]))  # Five identities, challenge_created; no experiment yet.
    content = {"artifact_hash": "a" * 64}
    with pytest.raises(Invalid, match="parent|result|lifecycle|stage"):
        w.run(
            3,
            "science_event",
            {
                "event_id": "premature-replication",
                "challenge_id": "science-1",
                "kind": "replication_registered",
                "agent_id": "agent-3",
                "parents": ["event-0"],
                "content": content,
                "content_hash": digest("tokoin.science.content.v03", content),
            },
        )


def test_invalidated_mature_review_cannot_authorize_new_result_reward():
    w = ScienceWorld()
    w.reviewed()
    w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "review-20"})
    w.run(0, "finalize", {"reward_id": "review-20"}, w.state["time"] + MATURITY)
    d = {
        "chain_id": w.genesis["chain_id"],
        "genesis_hash": w.state["genesis_hash"],
        "protocol_version": TX_VERSION,
        "reward_id": "review-20",
        "reward_hash": w.state["rewards"]["review-20"]["reward_hash"],
        "evidence_hash": "f" * 64,
    }
    w.run(
        2,
        "invalidate_finalized",
        {
            "decision": d,
            "signatures": {w.pubs[i]: sign(w.keys[i], "tokoin.invalidation.v3", d) for i in (0, 1)},
        },
    )
    before = w.state["created"]
    with pytest.raises(Invalid, match="review|invalid|prerequisite"):
        w.run(
            2,
            "science_settle_result",
            {
                "challenge_id": "science-1",
                "reward_id": "result-80",
                "solver_event_id": "event-5",
            },
        )
    assert w.state["created"] == before


def test_review_challenge_pause_is_preserved_in_dependent_result_maturity():
    w = ScienceWorld()
    settle_both(w)
    original_unlock = w.state["rewards"]["result-80"]["unlock_at"]
    challenge_review(w)
    paused_at = w.state["time"]
    w.run(2, "challenge_decide", reviewer_decision(w, "review-20", "REJECT"), paused_at + 100_000)
    with pytest.raises(Invalid, match="365|prerequisite|review|elapsed"):
        w.run(2, "finalize", {"reward_id": "result-80"}, original_unlock)
