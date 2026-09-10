"""Durable bounded A2A inbox. Remote tasks never grant local permissions.

An execution is recorded before calling a runtime. After a crash its effects
are ambiguous: report failure for reconciliation, never automatically repeat
it. Results remain durable until the server acknowledges its committed state.
"""

import fcntl
import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from agora_bridge.config import BridgeConfig, bridge_home
from agora_bridge.trust import wrap_untrusted

INBOX_LIMIT = 100
HISTORY_LIMIT = 25000
PAYLOAD_LIMIT = 1 << 20


def durable_inbox_path(config: BridgeConfig) -> Path | None:
    if not config.agent_id:
        return None
    identity = f"{config.api_url.rstrip('/')}|{config.agent_id}"
    return bridge_home() / "inbox" / f"{hashlib.sha256(identity.encode()).hexdigest()}.sqlite3"


def inbox_status(config: BridgeConfig) -> dict:
    """Read-only operational summary: no recovery, locking, payloads or credentials."""
    path = durable_inbox_path(config)
    if path is None or not path.exists():
        return {"exists": False, "counts": {}, "history_limit": HISTORY_LIMIT}
    if path.is_symlink():
        raise ValueError("refusing symlink inbox")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        counts = dict(db.execute("SELECT state,count(*) FROM inbox GROUP BY state"))
        pending = [
            {"task_id": task_id, "status": json.loads(result).get("status")}
            for task_id, result in db.execute(
                "SELECT task_id,result FROM inbox WHERE state='result_pending' LIMIT 100"
            )
        ]
        return {
            "exists": True,
            "counts": counts,
            "pending_receipts": pending,
            "history_limit": HISTORY_LIMIT,
            "active_limit": INBOX_LIMIT,
            "history_capacity_reached": sum(counts.values()) >= HISTORY_LIMIT,
            "automatic_reexecution_after_ambiguous_crash": False,
        }
    finally:
        db.close()


class A2AInbox:
    def __init__(self, limit: int = INBOX_LIMIT, path: Path | None = None):
        self.limit = limit
        self.duplicates_dropped = 0
        self.overflow_dropped = 0
        self.conflicts_dropped = 0
        self._lock = None
        if path is not None:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if path.is_symlink():
                raise ValueError("refusing symlink inbox")
            lock_path = path.with_suffix(".lock")
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            self._lock = os.fdopen(fd, "w")
            try:
                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self._lock.close()
                raise RuntimeError("another Bridge owns this durable inbox") from None
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            path.chmod(0o600)
        self._db = sqlite3.connect(str(path) if path else ":memory:")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS inbox (
            task_id TEXT PRIMARY KEY, frame TEXT NOT NULL, frame_hash TEXT NOT NULL,
            state TEXT NOT NULL, result TEXT, execution_id TEXT,
            created_at INTEGER NOT NULL DEFAULT (unixepoch())
        )""")
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(inbox)")}
        if "execution_id" not in columns:
            self._db.execute("ALTER TABLE inbox ADD COLUMN execution_id TEXT")
        for (task_id,) in self._db.execute("SELECT task_id FROM inbox WHERE execution_id IS NULL"):
            self._db.execute(
                "UPDATE inbox SET execution_id=? WHERE task_id=?", (str(uuid.uuid4()), task_id)
            )
        self._db.execute("UPDATE inbox SET state='queued' WHERE state='claiming'")
        # Only one owner holds the file lock. Rows left running are crash residue.
        for task_id, execution_id in self._db.execute(
            "SELECT task_id,execution_id FROM inbox WHERE state='running'"
        ):
            self._db.execute(
                "UPDATE inbox SET state='result_pending', result=? WHERE task_id=?",
                (
                    json.dumps(
                        {
                            "type": "a2a_result",
                            "task_id": task_id,
                            "status": "failed",
                            "execution_id": execution_id,
                            "artifacts": [],
                            "reason": "execution_interrupted_requires_reconciliation",
                        }
                    ),
                    task_id,
                ),
            )
        self._db.commit()

    def close(self) -> None:
        self._db.close()
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def offer(self, task_frame: dict[str, Any]) -> bool:
        task_id = task_frame.get("task_id")
        if not isinstance(task_id, str) or not task_id or len(task_id) > 256:
            return False
        encoded = json.dumps(task_frame, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode()) > PAYLOAD_LIMIT:
            return False
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        row = self._db.execute(
            "SELECT frame_hash FROM inbox WHERE task_id=?", (task_id,)
        ).fetchone()
        if row:
            self.duplicates_dropped += 1
            if row[0] != digest:
                self.conflicts_dropped += 1
            return False
        active = self._db.execute(
            "SELECT count(*) FROM inbox WHERE state!='acknowledged'"
        ).fetchone()[0]
        total = self._db.execute("SELECT count(*) FROM inbox").fetchone()[0]
        if active >= self.limit or total >= HISTORY_LIMIT:
            # Refuse new work; server retains pending tasks for future delivery.
            # Never evict dedup tombstones silently and risk executing old effects.
            self.overflow_dropped += 1
            return False
        with self._db:
            self._db.execute(
                "INSERT INTO inbox(task_id,frame,frame_hash,state,execution_id) "
                "VALUES(?,?,?,'queued',?)",
                (task_id, encoded, digest, str(uuid.uuid4())),
            )
        return True

    def take(self) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT task_id,frame FROM inbox WHERE state='queued' ORDER BY rowid LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        with self._db:
            self._db.execute("UPDATE inbox SET state='claiming' WHERE task_id=?", (row[0],))
        return wrap_untrusted(json.loads(row[1]), source="agora-a2a-relay")

    def execution_id(self, task_id: str) -> str:
        return self._db.execute(
            "SELECT execution_id FROM inbox WHERE task_id=?", (task_id,)
        ).fetchone()[0]

    def mark_running(self, task_id: str) -> None:
        with self._db:
            self._db.execute(
                "UPDATE inbox SET state='running' WHERE task_id=? AND state='claiming'", (task_id,)
            )

    def release_claim_wait(self, task_id: str, *, claimed_elsewhere: bool = False) -> None:
        with self._db:
            self._db.execute(
                "UPDATE inbox SET state=?,frame=CASE WHEN ? THEN '{}' ELSE frame END "
                "WHERE task_id=? AND state='claiming'",
                ("acknowledged" if claimed_elsewhere else "queued", claimed_elsewhere, task_id),
            )

    def save_result(
        self, task_id: str, artifacts: list, *, status: str = "completed", reason: str = ""
    ) -> dict:
        if status not in {"completed", "failed", "rejected"}:
            raise ValueError("unsupported result status")
        frame = {
            "type": "a2a_result",
            "task_id": task_id,
            "artifacts": artifacts,
            "status": status,
            "execution_id": self.execution_id(task_id),
        }
        if reason:
            frame["reason"] = reason[:256]
        encoded = json.dumps(frame)
        if len(encoded.encode()) > PAYLOAD_LIMIT:
            frame = {
                "type": "a2a_result",
                "task_id": task_id,
                "artifacts": [],
                "status": "failed",
                "reason": "result_exceeds_transport_limit",
                "execution_id": self.execution_id(task_id),
            }
            encoded = json.dumps(frame)
        with self._db:
            updated = self._db.execute(
                "UPDATE inbox SET state='result_pending',result=? "
                "WHERE task_id=? AND state='running'",
                (encoded, task_id),
            )
            if updated.rowcount != 1:
                raise ValueError("result requires a claimed local execution")
        return frame

    def pending_results(self) -> list[dict]:
        return [
            json.loads(row[0])
            for row in self._db.execute(
                "SELECT result FROM inbox WHERE state='result_pending' ORDER BY rowid"
            )
        ]

    def acknowledge(self, task_id: str, status: str) -> bool:
        row = self._db.execute(
            "SELECT result FROM inbox WHERE task_id=? AND state='result_pending'", (task_id,)
        ).fetchone()
        if row is None or json.loads(row[0]).get("status") != status:
            return False
        with self._db:
            # Retain identity/hash tombstone, discard potentially large content.
            self._db.execute(
                "UPDATE inbox SET state='acknowledged',frame='{}',result=NULL WHERE task_id=?",
                (task_id,),
            )
        return True

    def pending_count(self) -> int:
        return self._db.execute("SELECT count(*) FROM inbox WHERE state='queued'").fetchone()[0]
