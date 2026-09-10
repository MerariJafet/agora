"""Atomic node-local block journal, replayed from pinned genesis (not consensus)."""

import json
import sqlite3
import threading
from pathlib import Path

from .core import canonical, digest, initial_state, merkle, metrics, require, transition


class Store:
    def __init__(self, path: Path, genesis: dict):
        self.lock = threading.RLock()
        self.genesis = json.loads(canonical(genesis))
        self.state = initial_state(genesis)
        self.pending: tuple[dict, dict] | None = None
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS genesis (id INTEGER PRIMARY KEY, body TEXT)")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS blocks "
            "(height INTEGER PRIMARY KEY, body TEXT NOT NULL, state_root TEXT NOT NULL)"
        )
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT body FROM genesis WHERE id=1").fetchone()
            if row:
                require(row[0] == canonical(genesis).decode(), "genesis database mismatch")
            else:
                self.db.execute("INSERT INTO genesis VALUES (1,?)", (canonical(genesis).decode(),))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        self.last_block_hash = self.state["genesis_hash"]
        for height, raw, root in self.db.execute("SELECT * FROM blocks ORDER BY height"):
            block = json.loads(raw)
            require(
                block["height"] == height and block["previous_block_hash"] == self.last_block_hash,
                "corrupt journal linkage",
            )
            state = transition(
                genesis, self.state, block["transactions"], height, block["timestamp"]
            )
            expected = self._block(state, block["transactions"])
            require(
                block == expected and digest("tokoin.state.v2", state) == root,
                "corrupt journal/state",
            )
            self.state, self.last_block_hash = state, digest("tokoin.app-block.v2", block)

    def _block(self, state, transactions):
        return {
            "version": 2,
            "chain_id": self.genesis["chain_id"],
            "height": state["height"],
            "previous_block_hash": self.last_block_hash,
            "timestamp": state["time"],
            "transactions_root": merkle(transactions),
            "research_commitment_root": merkle(
                [[k, r["reward_hash"], r["status"]] for k, r in sorted(state["rewards"].items())]
            ),
            "state_root": digest("tokoin.state.v2", state),
            "transactions": transactions,
        }

    def prepare(self, transactions, height, timestamp):
        with self.lock:
            state = transition(self.genesis, self.state, transactions, height, timestamp)
            block = self._block(state, transactions)
            self.pending = (state, block)
            return state

    def commit(self):
        with self.lock:
            require(self.pending is not None, "nothing prepared")
            assert self.pending is not None
            state, block = self.pending
            self.db.execute("BEGIN IMMEDIATE")
            try:
                current = self.db.execute("SELECT coalesce(max(height),0) FROM blocks").fetchone()[
                    0
                ]
                require(current == self.state["height"], "concurrent stale state")
                self.db.execute(
                    "INSERT INTO blocks VALUES (?,?,?)",
                    (state["height"], canonical(block).decode(), block["state_root"]),
                )
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            self.state = state
            self.last_block_hash = digest("tokoin.app-block.v2", block)
            self.pending = None
            return self.state

    def export(self):
        with self.lock:
            return {
                "genesis": self.genesis,
                "metrics": metrics(self.state),
                "blocks": [
                    json.loads(r[0])
                    for r in self.db.execute("SELECT body FROM blocks ORDER BY height")
                ],
            }

    def manifest(self):
        with self.lock:
            # TEST manifests are audit artifacts. Economic importer must refuse them.
            allocations = [[k, v] for k, v in sorted(self.state["balances"].items()) if v]
            body = {
                "version": 2,
                "kind": "PILOT_GENESIS_MANIFEST_TEST_ONLY",
                "genesis_recognition_eligible": False,
                "mode": self.genesis["mode"],
                "chain_id": self.genesis["chain_id"],
                "height": self.state["height"],
                "genesis_hash": self.state["genesis_hash"],
                "history_root": self.last_block_hash,
                "state_root": digest("tokoin.state.v2", self.state),
                "created_units": self.state["created"],
                "recognized_economic_units": 0,
                "balances_root": merkle(allocations),
                "test_balances": allocations,
                "rewards": self.state["rewards"],
                "challenges": self.state["challenges"],
            }
            return {"manifest": body, "manifest_hash": digest("tokoin.pilot.manifest.v2", body)}

    def close(self):
        self.db.close()
