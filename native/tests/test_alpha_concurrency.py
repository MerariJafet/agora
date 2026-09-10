from concurrent.futures import ThreadPoolExecutor

from test_protocol import World

from tokoin_native.abci_server import Application
from tokoin_native.core import canonical, digest
from tokoin_native.store import Store
from tokoin_native.vendor.tendermint.abci import types_pb2 as pb


def test_128_concurrent_duplicate_nonces_settle_only_once(tmp_path):
    w = World()
    store = Store(tmp_path / 'concurrent.sqlite', w.genesis)
    app = Application(store)
    tx = canonical(w.tx(0, 'review_commit', {'reward_hash':'a'*64, 'commitment':'b'*64}))
    def check(_):
        return app.handle(pb.Request(check_tx=pb.RequestCheckTx(tx=tx))).check_tx.code
    with ThreadPoolExecutor(max_workers=16) as pool:
        # CheckTx is advisory and cannot reserve a consensus nonce.
        assert list(pool.map(check, range(128))) == [0]*128
    prepared = app.handle(pb.Request(prepare_proposal=pb.RequestPrepareProposal(
        txs=[tx]*128, height=1, time={'seconds':1001}, max_tx_bytes=1000000)))
    assert list(prepared.prepare_proposal.txs) == [tx]
    app.handle(pb.Request(finalize_block=pb.RequestFinalizeBlock(
        txs=[tx], height=1, time={'seconds':1001})))
    app.handle(pb.Request(commit=pb.RequestCommit()))
    assert store.state['nonces'][w.addresses[0]] == 1
    assert check(None) != 0
    store.close()


def test_restart_at_unlock_and_replay_cannot_double_finalize(tmp_path):
    w = World()
    path = tmp_path / 'unlock.sqlite'
    store = Store(path, w.genesis)
    original = w.run
    def record(*args, **kwargs):
        tx = original(*args, **kwargs)
        store.prepare([tx], w.state['height'], w.state['time'])
        store.commit()
        return tx
    w.run = record
    w.reward()
    unlock = store.state['rewards']['reward-1']['unlock_at']
    store.close()
    store = Store(path, w.genesis)
    tx = w.tx(2, 'finalize', {'reward_id':'reward-1'})
    app = Application(store)
    bad = app.handle(pb.Request(process_proposal=pb.RequestProcessProposal(
        txs=[canonical(tx)], height=store.state['height']+1, time={'seconds':unlock-1})))
    assert bad.process_proposal.status == pb.ResponseProcessProposal.REJECT
    store.prepare([tx], store.state['height']+1, unlock)
    store.commit()
    root = digest('tokoin.state.v2', store.state)
    store.close()
    store = Store(path, w.genesis)
    assert digest('tokoin.state.v2', store.state) == root
    app = Application(store)
    assert app.handle(pb.Request(check_tx=pb.RequestCheckTx(tx=canonical(tx)))).check_tx.code != 0
    store.close()
