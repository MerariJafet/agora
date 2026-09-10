"""Seeded bounded malformed-transaction corpus against the actual ABCI boundary."""
import json
import random

from test_protocol import World

from tokoin_native.abci_server import Application
from tokoin_native.core import canonical
from tokoin_native.store import Store
from tokoin_native.vendor.tendermint.abci import types_pb2 as pb


def test_seeded_malformed_transactions_fail_closed(tmp_path):
    rng = random.Random(20260910)
    w = World()
    store = Store(tmp_path / 'fuzz.sqlite', w.genesis)
    app = Application(store)
    before = canonical(store.state)
    values = [None, True, False, 0, -1, 1.5, [], {}, 'text', {'nonce': []}]
    corpus = [json.dumps(value, separators=(",", ":")).encode() for value in values]
    corpus += [bytes(rng.randrange(256) for _ in range(rng.randrange(1, 512))) for _ in range(2000)]
    corpus += [b'['*2000+b']'*2000, b'0'*64001]
    for raw in corpus:
        checked = app.handle(pb.Request(check_tx=pb.RequestCheckTx(tx=raw)))
        assert checked.check_tx.code != 0
        proposal = app.handle(pb.Request(process_proposal=pb.RequestProcessProposal(
            txs=[raw], height=1, time={'seconds':1001})))
        assert proposal.process_proposal.status == pb.ResponseProcessProposal.REJECT
        assert canonical(store.state) == before
    store.close()
