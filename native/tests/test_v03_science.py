import pytest
from test_protocol import World

from tokoin_native.core import MATURITY, UNIT, Invalid, canonical, digest, initial_state, transition
from tokoin_native.v03_science import PROTOCOL, commitment, genesis_v03, receipt, tree


class ScienceWorld(World):
    def __init__(self):
        super().__init__()
        identities = [
            {
                "agent_id": f"agent-{i}",
                "model": "TEST-fixture",
                "provider": "python-fixture",
                "passport_hash": digest("test.passport", i),
                "controller_group": f"group-{i}",
            }
            for i in range(5)
        ]
        self.genesis = genesis_v03(
            self.genesis,
            {
                self.pubs[i]: digest("tokoin.science.identity.v03", p)
                for i, p in enumerate(identities)
            },
        )
        self.state = initial_state(self.genesis)
        self.corpus = []
        for i, identity in enumerate(identities):
            self.run(i, "science_identity", identity)
        parent = []
        for number, kind in enumerate(
            [
                "challenge_created",
                "hypothesis_registered",
                "agent_contribution_registered",
                "evidence_committed",
                "experiment_registered",
                "experiment_result_committed",
                "replication_registered",
            ]
        ):
            content = {"artifact_hash": digest("test.artifact", number)}
            self.run(
                2 if number < 6 else 3,
                "science_event",
                {
                    "event_id": f"event-{number}",
                    "challenge_id": "science-1",
                    "kind": kind,
                    "agent_id": f"agent-{2 if number < 6 else 3}",
                    "parents": parent,
                    "content": content,
                    "content_hash": digest("tokoin.science.content.v03", content),
                },
            )
            parent = [f"event-{number}"]

    def run(self, *args, **kwargs):
        tx = super().run(*args, **kwargs)
        if hasattr(self, "corpus"):
            self.corpus.append(
                {"height": self.state["height"], "time": self.state["time"], "tx": tx}
            )
        return tx

    def reviewed(self, verdict="APPROVE"):
        self.bodies = []
        for i in (0, 1):
            body = {
                "review_id": f"review-{i}",
                "challenge_id": "science-1",
                "reviewer_identity": f"agent-{i}",
                "institution_identity_if_applicable": f"TEST-{i}",
                "methodology_assessment": "Measured method",
                "evidence_assessment": "Checked data",
                "replication_assessment": "Independent calculation",
                "verdict": verdict,
                "conflict_of_interest_declaration": {"has_conflict": False},
                "protocol_version": PROTOCOL,
                "contribution_tree_root": tree(self.state, "science-1"),
                "evidence_refs": ["event-4", "event-5", "event-6"],
            }
            self.bodies.append(body)
            self.run(
                i,
                "science_review_commit",
                {"challenge_id": "science-1", "commitment": commitment(body, str(i) * 64)},
            )
        for i in (0, 1):
            self.run(
                i,
                "science_review_reveal",
                {
                    "challenge_id": "science-1",
                    "receipt": receipt(self.keys[i], self.bodies[i], str(i) * 64),
                    "salt": str(i) * 64,
                },
            )
        self.run(2, "science_decide", {"challenge_id": "science-1"})
        self.run(
            2,
            "science_freeze",
            {"challenge_id": "science-1", "contribution_tree_root": tree(self.state, "science-1")},
        )


@pytest.mark.parametrize("verdict", ["APPROVE", "REJECT", "INCONCLUSIVE", "REQUEST_REPLICATION"])
def test_review_compensation_independent_of_verdict(verdict):
    w = ScienceWorld()
    w.reviewed(verdict)
    w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "review-reward"})
    reward = w.state["rewards"]["review-reward"]
    assert reward["authorization"]["reward_total"] == UNIT // 5
    assert reward["allocations"] == {w.addresses[0]: UNIT // 10, w.addresses[1]: UNIT // 10}
    assert reward["status"] == "LOCKED" and w.state["balances"] == {}
    with pytest.raises(Invalid):
        w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "other-id"})
    if verdict != "APPROVE":
        with pytest.raises(Invalid):
            w.run(
                2,
                "science_settle_result",
                {"challenge_id": "science-1", "reward_id": "result", "solver_event_id": "event-5"},
            )
    else:
        w.run(
            2,
            "science_settle_result",
            {"challenge_id": "science-1", "reward_id": "result", "solver_event_id": "event-5"},
        )
        assert w.state["created"] == UNIT
    replay = initial_state(w.genesis)
    for record in w.corpus:
        replay = transition(w.genesis, replay, [record["tx"]], record["height"], record["time"])
    assert canonical(replay) == canonical(w.state)


def test_no_science_bypass_and_no_identity_rebinding():
    w = ScienceWorld()
    with pytest.raises(Invalid, match="lifecycle"):
        w.run(2, "authorize", w.body())
    with pytest.raises(Invalid, match="identity immutable"):
        w.run(
            2,
            "science_identity",
            {
                "agent_id": "agent-2",
                "model": "changed",
                "provider": "fixture",
                "passport_hash": "a" * 64,
                "controller_group": "x",
            },
        )
    with pytest.raises(Invalid, match="state"):
        w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "too-early"})


def test_self_review_and_incomplete_method_rejected():
    w = ScienceWorld()
    with pytest.raises(Invalid, match="registered"):
        w.run(2, "science_review_commit", {"challenge_id": "science-1", "commitment": "a" * 64})
    # Even an epistemic identity cannot review its own contribution.
    content = {"artifact_hash": "e" * 64}
    w.run(
        0,
        "science_event",
        {
            "event_id": "self",
            "challenge_id": "science-1",
            "kind": "agent_contribution_registered",
            "agent_id": "agent-0",
            "parents": ["event-1"],
            "content": content,
            "content_hash": digest("tokoin.science.content.v03", content),
        },
    )
    with pytest.raises(Invalid, match="self review"):
        w.run(0, "science_review_commit", {"challenge_id": "science-1", "commitment": "a" * 64})


def test_review_reward_maturity_and_malformed_transaction_kind():
    w = ScienceWorld()
    w.reviewed("REJECT")
    w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "review-reward"})
    with pytest.raises(Invalid, match="365"):
        w.run(0, "finalize", {"reward_id": "review-reward"})
    w.run(0, "finalize", {"reward_id": "review-reward"}, w.state["time"] + MATURITY)
    assert w.state["balances"][w.addresses[0]] == UNIT // 10
    tx = w.tx(2, None, {})
    with pytest.raises(Invalid):
        transition(w.genesis, w.state, [tx], w.state["height"] + 1, w.state["time"] + 1)


def test_foreign_parent_atomic_rejection():
    w = ScienceWorld()
    before = canonical(w.state)
    content = {"a": "b"}
    with pytest.raises(Invalid, match="foreign"):
        w.run(
            2,
            "science_event",
            {
                "event_id": "bad",
                "challenge_id": "science-1",
                "kind": "replication_registered",
                "agent_id": "agent-2",
                "parents": ["foreign"],
                "content": content,
                "content_hash": digest("tokoin.science.content.v03", content),
            },
        )
    assert canonical(w.state) == before


@pytest.mark.parametrize(
    "field,bad",
    [("kind", []), ("parents", [{}]), ("agent_id", {}), ("challenge_id", []), ("content", [])],
)
def test_malformed_scientific_events_fail_closed(field, bad):
    w = ScienceWorld()
    content = {"artifact_hash": "a" * 64}
    p = {
        "event_id": "bad-event",
        "challenge_id": "science-1",
        "kind": "replication_registered",
        "agent_id": "agent-3",
        "parents": ["event-5"],
        "content": content,
        "content_hash": digest("tokoin.science.content.v03", content),
    }
    p[field] = bad
    before = canonical(w.state)
    with pytest.raises(Invalid):
        w.run(3, "science_event", p)
    assert canonical(w.state) == before


def test_v03_review_cap_exact_and_one_unit_over_atomic():
    from tokoin_native.core import PILOT_CAP, invariant

    w = ScienceWorld()
    w.reviewed("REJECT")
    # Deliberate unit-test boundary state; never a ledger/network fixture.
    w.state["created"] = PILOT_CAP - UNIT // 5 + 1
    w.state["revoked"] = w.state["created"]
    invariant(w.state)
    before = canonical(w.state)
    with pytest.raises(Invalid):
        w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "cap"})
    assert canonical(w.state) == before
    w.state["created"] -= 1
    w.state["revoked"] -= 1
    w.run(2, "science_settle_review", {"challenge_id": "science-1", "reward_id": "cap"})
    assert w.state["created"] == PILOT_CAP
