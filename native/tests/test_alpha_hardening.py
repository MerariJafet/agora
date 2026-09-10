import copy
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from test_protocol import World

from tokoin_native.abci_server import Application, decode
from tokoin_native.core import (
    MATURITY,
    TX_VERSION,
    Invalid,
    canonical,
    initial_state,
    transition,
)
from tokoin_native.store import Store
from tokoin_native.wallet import sign


@pytest.mark.parametrize(
    "mutation",
    [
        "chain_id",
        "genesis_hash",
        "protocol_version",
        "kind",
        "sender",
        "payload_hash",
        "public_key",
        "nonce_future",
        "nonce_old",
    ],
)
def test_transaction_all_domains(mutation):
    w = World()
    tx = w.tx(0, "review_commit", {"reward_hash": "a" * 64, "commitment": "b" * 64})
    if mutation == "nonce_future":
        tx["nonce"] += 2
    elif mutation == "nonce_old":
        tx["nonce"] = 0
    else:
        tx[mutation] = "wrong"
    with pytest.raises(Invalid):
        transition(w.genesis, w.state, [tx], 1, 1001)


def test_same_chain_different_genesis_replay_regression():
    w = World()
    tx = w.tx(0, "review_commit", {"reward_hash": "a" * 64, "commitment": "b" * 64})
    g = copy.deepcopy(w.genesis)
    g["timestamp"] += 1
    with pytest.raises(Invalid, match="genesis"):
        transition(g, initial_state(g), [tx], 1, 1001)


@pytest.mark.parametrize("delta,valid", [(-1, False), (0, True), (1, True), (10**9, True)])
def test_persisted_unlock_boundaries(delta, valid):
    w = World()
    w.reward()
    unlock = w.state["rewards"]["reward-1"]["unlock_at"]
    before = canonical(w.state)
    if valid:
        w.run(2, "finalize", {"reward_id": "reward-1"}, unlock + delta)
        assert w.state["rewards"]["reward-1"]["status"] == "FINALIZED"
    else:
        with pytest.raises(Invalid):
            w.run(2, "finalize", {"reward_id": "reward-1"}, unlock + delta)
        assert canonical(w.state) == before


def test_post_maturity_invalidation_never_claws_back():
    w = World()
    w.reward()
    w.run(2, "finalize", {"reward_id": "reward-1"}, w.state["time"] + MATURITY)
    w.run(2, "transfer", {"to": w.addresses[3], "amount": 1})
    balances = copy.deepcopy(w.state["balances"])
    created = w.state["created"]
    d = {
        "chain_id": w.genesis["chain_id"],
        "genesis_hash": w.state["genesis_hash"],
        "protocol_version": TX_VERSION,
        "reward_id": "reward-1",
        "reward_hash": w.state["rewards"]["reward-1"]["reward_hash"],
        "evidence_hash": "e" * 64,
    }
    payload = {
        "decision": d,
        "signatures": {w.pubs[i]: sign(w.keys[i], "tokoin.invalidation.v3", d) for i in (0, 1)},
    }
    w.run(3, "invalidate_finalized", payload)
    assert w.state["balances"] == balances and w.state["created"] == created
    assert w.state["rewards"]["reward-1"]["scientific_status"] == "INVALIDATED_AFTER_MATURITY"
    with pytest.raises(Invalid):
        w.run(3, "invalidate_finalized", payload)


def test_appeal_bound_and_stale_decision_replay():
    w = World()
    w.reward()
    w.challenge()
    old = w.decision("ADMIT")
    w.run(3, "challenge_decide", w.decision("REJECT"))
    w.run(
        3,
        "challenge_appeal",
        {"challenge_id": "challenge-1", "evidence_hash": "9" * 64, "method_hash": "8" * 64},
    )
    with pytest.raises(Invalid, match="revision"):
        w.run(3, "challenge_decide", old)
    w.run(3, "challenge_decide", w.decision("ADMIT"))
    w.run(3, "challenge_decide", w.decision("REJECT"))
    with pytest.raises(Invalid, match="limit"):
        w.run(
            3,
            "challenge_appeal",
            {"challenge_id": "challenge-1", "evidence_hash": "7" * 64, "method_hash": "8" * 64},
        )


def test_changed_method_cannot_repeat_same_evidence():
    w = World()
    w.reward()
    w.challenge()
    p = copy.deepcopy(w.state["challenges"]["challenge-1"]["submission"])
    p.update(challenge_id="duplicate-other-id", method_hash="1" * 64)
    with pytest.raises(Invalid, match="duplicate evidence"):
        w.run(3, "challenge_submit", p)


@pytest.mark.parametrize("corruption", ["delete", "modify", "duplicate"])
def test_journal_damage_detected(tmp_path, corruption):
    w = World()
    db = tmp_path / "node.sqlite"
    s = Store(db, w.genesis)
    s.prepare([], 1, 1001)
    s.commit()
    s.close()
    con = sqlite3.connect(db)
    if corruption == "delete":
        con.execute("DELETE FROM blocks WHERE height=1")
    if corruption == "modify":
        con.execute("UPDATE blocks SET body='{}' WHERE height=1")
    if corruption == "duplicate":
        con.execute("INSERT INTO blocks SELECT 2,body,state_root FROM blocks WHERE height=1")
    con.commit()
    con.close()
    with pytest.raises((Invalid, KeyError)):
        Store(db, w.genesis)


CRASH_SCRIPT = r"""
import os,json,sys
from pathlib import Path
from tokoin_native.store import Store
from tokoin_native.abci_server import Application
from tokoin_native.vendor.tendermint.abci import types_pb2 as pb
p=Path(sys.argv[1]);point=sys.argv[2]
def fault(name):
 if point==name:os._exit(73)
g=json.loads((p/'genesis.json').read_text());s=Store(p/'node.sqlite',g,fault)
a=Application(s)
prepare=pb.RequestPrepareProposal(height=2,max_tx_bytes=1000000);prepare.time.seconds=1002
a.handle(pb.Request(prepare_proposal=prepare))
process=pb.RequestProcessProposal(height=2);process.time.seconds=1002
a.handle(pb.Request(process_proposal=process))
s.prepare([],2,1002);s.commit()
"""


@pytest.mark.parametrize(
    "point",
    [
        "before_prepare_proposal",
        "after_prepare_proposal",
        "before_process_proposal",
        "after_process_proposal",
        "finalize_start",
        "after_finalize",
        "before_commit",
        "before_persistence",
        "during_journal_write",
        "after_fsync",
        "after_commit",
    ],
)
def test_real_crash_points(tmp_path, point):
    w = World()
    (tmp_path / "genesis.json").write_bytes(canonical(w.genesis))
    s = Store(tmp_path / "node.sqlite", w.genesis)
    s.prepare([], 1, 1001)
    s.commit()
    s.close()
    result = subprocess.run(  # noqa: S603 - fixed isolated crash-test child

        [sys.executable, "-c", CRASH_SCRIPT, str(tmp_path), point],
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True,
    )
    assert result.returncode == 73, result.stderr.decode()
    s = Store(tmp_path / "node.sqlite", w.genesis)
    assert s.state["height"] == (2 if point in ("after_fsync", "after_commit") else 1)
    expected = transition(w.genesis, initial_state(w.genesis), [], 1, 1001)
    if s.state["height"] == 2:
        expected = transition(w.genesis, expected, [], 2, 1002)
    assert canonical(s.state) == canonical(expected)
    s.close()


def test_mid_transaction_crash_replays_committed_only(tmp_path):
    w = World()
    (tmp_path / "genesis.json").write_bytes(canonical(w.genesis))
    transactions = [
        w.tx(i, "review_commit", {"reward_hash": "a" * 64, "commitment": str(i) * 64})
        for i in (0, 1)
    ]
    (tmp_path / "txs.json").write_bytes(canonical(transactions))
    s = Store(tmp_path / "node.sqlite", w.genesis)
    s.prepare([], 1, 1001)
    s.commit()
    s.close()
    code = r"""
import sys,os,json
from pathlib import Path
from tokoin_native import core
from tokoin_native.store import Store
p=Path(sys.argv[1]);s=Store(p/'node.sqlite',json.loads((p/'genesis.json').read_text()))
original=core._apply
def crash(*args):
 original(*args)
 os._exit(73)
core._apply=crash
s.prepare(json.loads((p/'txs.json').read_text()),2,1002)
"""
    result = subprocess.run(  # noqa: S603 - fixed isolated crash-test child

        [sys.executable, "-c", code, str(tmp_path)],
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True,
    )
    assert result.returncode == 73
    s = Store(tmp_path / "node.sqlite", w.genesis)
    assert s.state["height"] == 1 and s.state["reviews"] == {} and s.state["created"] == 0
    s.close()


def test_time_guard_aliases_and_dynamic_access():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "time_policy", Path(__file__).resolve().parents[1] / "tools/time_policy.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for source in [
        "from time import time as hidden",
        "import datetime as d",
        'x=__import__("time")',
        'x=getattr(obj,"now")',
    ]:
        assert module.violations(source)
    assert module.inspect()["status"] == "PASS"


def test_malformed_and_snapshot_fail_closed(tmp_path):
    from tokoin_native.vendor.tendermint.abci import types_pb2 as pb

    for raw in [b"{", b"x" * 64001, b'{"a":1,"a":2}', b"[]" * 100]:
        with pytest.raises((Invalid, ValueError)):
            decode(raw)
    w = World()
    s = Store(tmp_path / "node.sqlite", w.genesis)
    a = Application(s)
    result = a.handle(pb.Request(offer_snapshot=pb.RequestOfferSnapshot()))
    assert result.offer_snapshot.result == pb.ResponseOfferSnapshot.REJECT
    assert s.state["height"] == 0
    s.close()


def test_explorer_preserves_post_finality_evidence(tmp_path):
    from tokoin_native.explorer import render
    w = World()
    store = Store(tmp_path / "explorer.sqlite", w.genesis)
    w.reward()
    w.state["rewards"]["reward-1"]["scientific_status"] = "INVALIDATED_AFTER_MATURITY"
    w.state["rewards"]["reward-1"]["scientific_invalidations"] = [{"evidence_hash": "<unsafe>"}]
    # Rendering fixture only; protocol invalidation is tested separately above.
    store.state = w.state
    page = render(store)
    assert "INVALIDATED_AFTER_MATURITY" in page
    assert "&lt;unsafe&gt;" in page and "<unsafe>" not in page
    store.close()
