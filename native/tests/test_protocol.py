import copy
import random
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tokoin_native.core import (
    MATURITY,
    MAX_SUPPLY,
    PILOT_CAP,
    TX_VERSION,
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
    metrics,
    review_commitment,
    split_weighted,
    transition,
)
from tokoin_native.store import Store
from tokoin_native.wallet import load_key, public_key, save_key, sign, transaction


class World:
    def __init__(self):
        self.keys = [Ed25519PrivateKey.generate() for _ in range(5)]
        self.pubs = [public_key(k) for k in self.keys]
        self.addresses = [address(p) for p in self.pubs]
        registry = {
            self.pubs[i]: {
                "institution_id": f"TEST-{i}",
                "controller_group": f"owner-{i}",
                "payout_address": self.addresses[i],
                "label": "INSTITUTIONAL_VALIDATOR_TEST",
            }
            for i in (0, 1)
        }
        self.genesis = make_genesis("tokoin-test-suite", registry, self.addresses[4], 1000)
        self.state = initial_state(self.genesis)

    def tx(self, i, kind, payload, state=None):
        state = state or self.state
        return transaction(
            self.keys[i],
            self.genesis,
            state["nonces"].get(self.addresses[i], 0) + 1,
            kind,
            payload,
        )

    def run(self, i, kind, payload, timestamp=None):
        tx = self.tx(i, kind, payload)
        self.state = transition(
            self.genesis,
            self.state,
            [tx],
            self.state["height"] + 1,
            self.state["time"] + 1 if timestamp is None else timestamp,
        )
        return tx

    def body(self, number=1, research=None):
        groups = {
            "proposer": {self.addresses[2]: 1},
            "solver": {self.addresses[2]: 1},
            "contributors": {self.addresses[2]: 3, self.addresses[3]: 1},
            "institutions": {self.addresses[0]: 1, self.addresses[1]: 1},
            "infra": {self.addresses[4]: 1},
        }
        allocations = distribution(UNIT, groups)
        return {
            "reward_id": f"reward-{number}",
            "research_id": research or f"research-{number}",
            "candidate_version": number,
            "protocol_version": VERSION,
            "genealogy_root": digest("test", ["graph", number]),
            "paper_hash": "a" * 64,
            "dataset_manifest_hash": "b" * 64,
            "code_manifest_hash": "c" * 64,
            "reward_total": UNIT,
            "groups": groups,
            "distribution_root": merkle([[k, v] for k, v in allocations.items()]),
            "participant_controllers": ["researcher-owner"],
        }

    def reviews(self, body, verdicts=("APPROVED", "APPROVED")):
        h = authorization_hash(body)
        for i in (0, 1):
            self.run(
                i,
                "review_commit",
                {"reward_hash": h, "commitment": review_commitment(h, verdicts[i], str(i) * 64)},
            )
        for i in (0, 1):
            self.run(
                i, "review_reveal", {"reward_hash": h, "verdict": verdicts[i], "salt": str(i) * 64}
            )

    def reward(self, number=1, research=None):
        body = self.body(number, research)
        self.reviews(body)
        self.run(2, "authorize", body)
        return body

    def challenge(self):
        self.run(
            3,
            "challenge_submit",
            {
                "challenge_id": "challenge-1",
                "reward_id": "reward-1",
                "target_claim_hash": "d" * 64,
                "evidence_hash": "e" * 64,
                "method_hash": "f" * 64,
            },
        )

    def decision(self, outcome):
        d = {
            "chain_id": self.genesis["chain_id"],
            "genesis_hash": self.state["genesis_hash"],
            "protocol_version": TX_VERSION,
            "challenge_revision": self.state["challenges"]["challenge-1"]["revision"],
            "challenge_id": "challenge-1",
            "reward_id": "reward-1",
            "reward_hash": self.state["rewards"]["reward-1"]["reward_hash"],
            "outcome": outcome,
        }
        return {
            "decision": d,
            "signatures": {
                self.pubs[i]: sign(self.keys[i], "tokoin.challenge.decision.v3", d) for i in (0, 1)
            },
        }


@pytest.fixture
def world():
    return World()


def test_zero_genesis_no_treasury(world):
    assert world.state["created"] == 0 and world.state["balances"] == {}
    altered = copy.deepcopy(world.genesis)
    altered["max_supply_units"] += 1
    with pytest.raises(Invalid):
        initial_state(altered)
    altered = copy.deepcopy(world.genesis)
    altered["mode"] = "MAINNET"
    with pytest.raises(Invalid):
        initial_state(altered)


@pytest.mark.parametrize("amount", [True, 1.0, "1", -1, 0, MAX_SUPPLY + 1])
def test_strict_amounts(amount):
    with pytest.raises(Invalid):
        check_capacity(0, amount)


def test_limits_one_minimal_unit():
    check_capacity(0, MAX_SUPPLY, pilot=False)
    check_capacity(PILOT_CAP - 1, 1)
    with pytest.raises(Invalid, match="pilot cap"):
        check_capacity(PILOT_CAP, 1)
    with pytest.raises(Invalid):
        check_capacity(MAX_SUPPLY, 1, pilot=False)


def test_weighted_conservation_properties(world):
    rng = random.Random(39210)
    for _ in range(1000):
        total = rng.randrange(0, MAX_SUPPLY + 1)
        weights = dict(
            zip(world.addresses, (rng.randrange(1, 1000) for _ in range(5)), strict=True)
        )
        result = split_weighted(total, weights)
        assert sum(result.values()) == total
        assert result == split_weighted(total, dict(reversed(list(weights.items()))))


def test_success_locked_finalized_transfer(world):
    world.reward()
    assert metrics(world.state)["locked_units"] == UNIT
    with pytest.raises(Invalid, match="insufficient"):
        world.run(2, "transfer", {"to": world.addresses[3], "amount": 1})
    start = world.state["time"]
    with pytest.raises(Invalid, match="365 days"):
        world.run(2, "finalize", {"reward_id": "reward-1"}, start + MATURITY - 1)
    world.run(2, "finalize", {"reward_id": "reward-1"}, start + MATURITY)
    world.run(2, "transfer", {"to": world.addresses[3], "amount": 1})
    invariant(world.state)
    assert sum(world.state["balances"].values()) == UNIT
    with pytest.raises(Invalid):
        world.run(2, "finalize", {"reward_id": "reward-1"})


@pytest.mark.parametrize("verdict", ["REJECTED", "REQUIRES_REVISION", "INSUFFICIENT_EVIDENCE"])
def test_disagree_no_issuance(world, verdict):
    body = world.body()
    world.reviews(body, ("APPROVED", verdict))
    with pytest.raises(Invalid, match="compatible"):
        world.run(2, "authorize", body)
    assert world.state["created"] == 0


def test_forged_single_and_early_reveal(world):
    body = world.body()
    h = authorization_hash(body)
    p = {"reward_hash": h, "commitment": review_commitment(h, "APPROVED", "0" * 64)}
    with pytest.raises(Invalid, match="unregistered"):
        world.run(2, "review_commit", p)
    world.run(0, "review_commit", p)
    with pytest.raises(Invalid):
        world.run(0, "review_reveal", {"reward_hash": h, "verdict": "APPROVED", "salt": "0" * 64})
    with pytest.raises(Invalid):
        world.run(2, "authorize", body)


def test_signature_replay_cross_chain_atomic(world):
    body = world.body()
    world.reviews(body)
    tx = world.tx(2, "authorize", body)
    tampered = copy.deepcopy(tx)
    tampered["payload"]["reward_total"] += 1
    original = canonical(world.state)
    for bad in (tampered, tx | {"chain_id": "tokoin-test-other"}, tx | {"signature": "0" * 128}):
        with pytest.raises(Invalid):
            transition(
                world.genesis,
                world.state,
                [bad],
                world.state["height"] + 1,
                world.state["time"] + 1,
            )
        assert canonical(world.state) == original
    next_state = transition(
        world.genesis, world.state, [tx], world.state["height"] + 1, world.state["time"] + 1
    )
    with pytest.raises(Invalid, match="nonce"):
        transition(
            world.genesis, next_state, [tx], next_state["height"] + 1, next_state["time"] + 1
        )


def test_authorization_replay_new_id_same_research(world):
    world.reward()
    body = world.body(2, "research-1")
    world.reviews(body)
    with pytest.raises(Invalid, match="research already"):
        world.run(2, "authorize", body)


@pytest.mark.parametrize("outcome", ["REJECT", "MINOR"])
def test_day364_pauses_does_not_reset(world, outcome):
    world.reward()
    start = world.state["time"]
    world.state = transition(
        world.genesis, world.state, [], world.state["height"] + 1, start + 364 * 86400
    )
    world.challenge()
    world.run(3, "challenge_decide", world.decision("ADMIT"))
    elapsed = world.state["rewards"]["reward-1"]["elapsed"]
    world.state = transition(
        world.genesis, world.state, [], world.state["height"] + 1, world.state["time"] + 100 * 86400
    )
    with pytest.raises(Invalid):
        world.run(2, "finalize", {"reward_id": "reward-1"})
    world.run(3, "challenge_decide", world.decision(outcome))
    resumed = world.state["time"]
    with pytest.raises(Invalid):
        world.run(2, "finalize", {"reward_id": "reward-1"}, resumed + MATURITY - elapsed - 1)
    world.run(2, "finalize", {"reward_id": "reward-1"}, resumed + MATURITY - elapsed)


def test_material_resets_new_candidate_lifetime_cap(world):
    world.reward()
    world.challenge()
    world.run(3, "challenge_decide", world.decision("ADMIT"))
    world.run(3, "challenge_decide", world.decision("MATERIAL"))
    assert world.state["created"] == world.state["revoked"] == UNIT
    world.reward(2, "research-1")
    assert world.state["rewards"]["reward-2"]["elapsed"] == 0
    assert world.state["created"] == 2 * UNIT
    with pytest.raises(Invalid):
        world.run(2, "finalize", {"reward_id": "reward-2"}, world.state["time"] + MATURITY - 1)


def test_unadmitted_hash_only_challenge_does_not_block(world):
    world.reward()
    start = world.state["time"]
    world.challenge()
    world.run(2, "finalize", {"reward_id": "reward-1"}, start + MATURITY)
    assert world.state["challenges"]["challenge-1"]["state"] == "SUBMITTED"


def test_invalid_challenge_does_not_reset(world):
    world.reward()
    start = world.state["time"]
    world.challenge()
    world.run(3, "challenge_decide", world.decision("REJECT"))
    world.run(2, "finalize", {"reward_id": "reward-1"}, start + MATURITY)


def test_double_spend_atomic(world):
    world.reward()
    world.run(2, "finalize", {"reward_id": "reward-1"}, world.state["time"] + MATURITY)
    amount = world.state["balances"][world.addresses[2]]
    tx = world.tx(2, "transfer", {"to": world.addresses[3], "amount": amount})
    tx2 = transaction(
        world.keys[2],
        world.genesis,
        tx["nonce"] + 1,
        "transfer",
        {"to": world.addresses[3], "amount": amount},
    )
    before = canonical(world.state)
    with pytest.raises(Invalid):
        transition(
            world.genesis,
            world.state,
            [tx, tx2],
            world.state["height"] + 1,
            world.state["time"] + 1,
        )
    assert canonical(world.state) == before


def test_two_rewards_cap_atomic(world):
    bodies = [world.body(1), world.body(2)]
    for body in bodies:
        world.reviews(body)
    # Generated reachable accounting fixture near cap; no public state import exists.
    world.state["created"] = PILOT_CAP - UNIT
    world.state["revoked"] = PILOT_CAP - UNIT
    invariant(world.state)
    tx = world.tx(2, "authorize", bodies[0])
    tx2 = transaction(world.keys[2], world.genesis, tx["nonce"] + 1, "authorize", bodies[1])
    with pytest.raises(Invalid, match="pilot cap"):
        transition(
            world.genesis,
            world.state,
            [tx, tx2],
            world.state["height"] + 1,
            world.state["time"] + 1,
        )
    world.run(2, "authorize", bodies[0])
    assert world.state["created"] == PILOT_CAP


def test_journal_restart_and_tamper(tmp_path, world):
    db = tmp_path / "node.sqlite"
    store = Store(db, world.genesis)
    store.prepare([], 1, 1001)
    store.close()  # crash before commit: provisional state must not escape
    store = Store(db, world.genesis)
    assert store.state["height"] == 0
    store.prepare([], 1, 1001)
    store.commit()
    manifest = store.manifest()
    store.close()
    store = Store(db, world.genesis)
    assert store.state["height"] == 1 and store.manifest() == manifest
    store.close()
    conn = sqlite3.connect(db)
    conn.execute("UPDATE blocks SET state_root='corrupt'")
    conn.commit()
    conn.close()
    with pytest.raises(Invalid, match="corrupt"):
        Store(db, world.genesis)


def test_concurrent_store_commit_only_once(tmp_path, world):
    a, b = (Store(tmp_path / "node.sqlite", world.genesis) for _ in range(2))
    a.prepare([], 1, 1001)
    b.prepare([], 1, 1001)

    def commit(store):
        try:
            store.commit()
            return True
        except Invalid:
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(commit, (a, b))) == [False, True]
    a.close()
    b.close()


def test_encrypted_wallet(tmp_path):
    path = tmp_path / "wallet.pem"
    pub = save_key(path, b"long-test-password-1234")
    assert b"ENCRYPTED PRIVATE KEY" in path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    assert public_key(load_key(path, b"long-test-password-1234")) == pub
    with pytest.raises(ValueError):
        load_key(path, b"wrong")
    with pytest.raises(FileExistsError):
        save_key(path, b"long-test-password-1234")


def test_deterministic_genesis_manifest_and_no_recognition(tmp_path, world):
    stores = [Store(tmp_path / f"{i}.sqlite", world.genesis) for i in range(3)]
    for store in stores:
        store.prepare([], 1, 1001)
        store.commit()
    assert len({canonical(s.manifest()) for s in stores}) == 1
    assert stores[0].manifest()["manifest"]["recognized_economic_units"] == 0
    for store in stores:
        store.close()


def test_merkle_count_unambiguous():
    assert merkle(["a", "b", "c"]) != merkle(["a", "b", "c", "c"])


def test_deep_json_and_duplicate_encoding_rejected():
    from tokoin_native.abci_server import decode

    for raw in (
        b"[" * 1100 + b"0" + b"]" * 1100,
        b"[" * 60 + b"0" + b"]" * 60,
        b'{"a":1,"a":2}',
        b'{"a":1.0}',
    ):
        with pytest.raises(Invalid):
            decode(raw)


def test_abci_survives_nested_input_and_rejects_wrong_consensus(tmp_path, world):
    import socket
    import threading

    from tokoin_native.abci_server import Application, Handler, Server, frame, read_frame
    from tokoin_native.vendor.tendermint.abci import types_pb2 as pb

    store = Store(tmp_path / "node.sqlite", world.genesis)
    with Server(("127.0.0.1", 0), Handler) as server:
        server.application = Application(store)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with socket.create_connection(server.server_address, timeout=3) as client:
                stream = client.makefile("rwb", buffering=0)
                request = pb.Request(
                    check_tx=pb.RequestCheckTx(tx=b"[" * 1100 + b"0" + b"]" * 1100)
                )
                stream.write(frame(request.SerializeToString()))
                assert pb.Response.FromString(read_frame(stream)).check_tx.code == 1
                stream.write(frame(pb.Request(info=pb.RequestInfo()).SerializeToString()))
                assert pb.Response.FromString(read_frame(stream)).info.last_block_height == 0
        finally:
            server.shutdown()
            worker.join(3)
    app = Application(store)
    request = pb.RequestInitChain(
        chain_id=world.genesis["chain_id"],
        app_state_bytes=canonical(world.genesis),
        initial_height=1,
    )
    request.time.seconds = world.genesis["timestamp"]
    with pytest.raises(Invalid, match="validator set"):
        app.handle(pb.Request(init_chain=request))
    store.close()


def test_wrong_decision_signer_and_cross_candidate(world):
    world.reward()
    world.challenge()
    decision = world.decision("ADMIT")
    del decision["signatures"][world.pubs[1]]
    with pytest.raises(Invalid):
        world.run(3, "challenge_decide", decision)
    decision = world.decision("ADMIT")
    decision["decision"]["reward_hash"] = "0" * 64
    with pytest.raises(Invalid):
        world.run(3, "challenge_decide", decision)
    assert world.state["rewards"]["reward-1"]["status"] == "LOCKED"


def test_model_simulations_conserve_caps():
    from tokoin_native.simulation import simulate

    report = simulate()
    assert len(report["rows"]) == 12
    for row in report["rows"]:
        total = 0
        for annual in row["annual"]:
            total += annual["issued_units"]
            assert annual["remaining_units"] == MAX_SUPPLY - total >= 0
        assert set(row["horizons"]) == {"10", "25", "50", "100"}


def test_agora_bridge_reuses_verified_package_and_never_submits(tmp_path, world):
    import importlib.util
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "native_prepare", root / "native/tools/prepare_agora_reward.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Existing public TEST export; no API/DB mutation or invented institutional review.
    package = json.loads(
        (root / "native/tests/fixtures/agora-public-test-package.json").read_text()
    )
    files = {}
    for name in ("paper", "dataset_manifest", "code_manifest"):
        path = tmp_path / name
        path.write_text("TEST fixture bytes; not scientific evidence")
        files[name] = path
    body = world.body()
    plan = {
        "reward_id": "TEST-bridge",
        "groups": body["groups"],
        "participant_controllers": body["participant_controllers"],
    }
    draft = module.prepare(package, package["candidate"]["content_hash"], plan, files)
    assert draft["source_integrity"]["integrity_verified"] is True
    assert draft["submitted"] is False and draft["signed"] is False
    assert (
        draft["authorization"]["genealogy_root"]
        == package["candidate"]["canonical_payload"]["knowledge_root_hash"]
    )
    with pytest.raises(ValueError):
        module.prepare(package, "0" * 64, plan, files)


def test_conflicting_height_and_backward_time_rejected(world):
    previous = transition(world.genesis, world.state, [], 1, 2000)
    for height, timestamp in ((1, 2001), (3, 2001), (2, 1999)):
        with pytest.raises(Invalid):
            transition(world.genesis, previous, [], height, timestamp)
    assert previous["height"] == 1


def test_conflicting_ownership_and_arbitrary_amount_rejected(world):
    body = world.body()
    body["participant_controllers"] = ["owner-0"]
    world.reviews(body)
    with pytest.raises(Invalid, match="conflict"):
        world.run(2, "authorize", body)
    body = world.body(2)
    body["reward_total"] += 1
    world.reviews(body)
    with pytest.raises(Invalid, match="fixed TEST reward"):
        world.run(2, "authorize", body)
