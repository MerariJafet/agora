"""Real SQLite storage failures; never change the host filesystem or live database."""
import sqlite3

import pytest
from test_protocol import World

from tokoin_native.core import canonical
from tokoin_native.store import Store


def test_full_database_rolls_back_and_recovers(tmp_path):
    w = World()
    path = tmp_path / 'full.sqlite'
    store = Store(path, w.genesis)
    before = canonical(store.state)
    # SQLite's real page allocator returns SQLITE_FULL at this quota.
    pages = store.db.execute('PRAGMA page_count').fetchone()[0]
    store.db.execute(f'PRAGMA max_page_count={pages}')
    txs = []
    for i in range(40):
        tx = w.run(0, 'review_commit', {'reward_hash': f'{i:064x}', 'commitment': 'b'*64})
        txs.append(tx)
    store.prepare(txs, 1, 1100)
    with pytest.raises(sqlite3.OperationalError, match='full'):
        store.commit()
    assert canonical(store.state) == before
    assert store.db.execute('SELECT count(*) FROM blocks').fetchone()[0] == 0
    store.db.execute('PRAGMA max_page_count=100000')
    store.commit()
    expected = canonical(store.state)
    store.close()
    recovered = Store(path, w.genesis)
    assert canonical(recovered.state) == expected
    recovered.close()


def test_read_only_commit_does_not_promote_working_state(tmp_path):
    w = World()
    store = Store(tmp_path / 'readonly.sqlite', w.genesis)
    before = canonical(store.state)
    store.prepare([], 1, 1001)
    store.db.execute('PRAGMA query_only=ON')
    with pytest.raises(sqlite3.OperationalError, match='readonly'):
        store.commit()
    assert canonical(store.state) == before
    store.db.execute('PRAGMA query_only=OFF')
    store.commit()
    assert store.state['height'] == 1
    store.close()
