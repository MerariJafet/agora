"""Run against pinned native source; independent account operations commute."""
import json
import tempfile
from pathlib import Path
from test_protocol import World
from tokoin_native.core import canonical, digest
from tokoin_native.store import Store

w = World()
a = w.tx(0,'review_commit',{'reward_hash':'a'*64,'commitment':'b'*64})
b = w.tx(1,'review_commit',{'reward_hash':'c'*64,'commitment':'d'*64})
roots=[]
with tempfile.TemporaryDirectory(prefix='tokoin-order-TEST-') as directory:
    for i,txs in enumerate(([a,b],[b,a],[a,b],[b,a])):
        store=Store(Path(directory)/f'{i}.sqlite',w.genesis)
        store.prepare(txs,1,1001);store.commit()
        roots.append(digest('tokoin.state.v2',store.state));store.close()
assert len(set(roots)) == 1
print(json.dumps({'status':'PASS','genesis':w.genesis,'transactions':[a,b],'height':1,'protocol_time':1001,'app_hashes':roots,'scope':'four stores, two arrival orders, independent account review commits','does_not_claim_dependent_transactions_commute':True}))
