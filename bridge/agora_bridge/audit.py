"""LocalAuditLog: append-only JSONL of actions and policy decisions.

Never records secrets or key material — entries are structured and the
writer rejects secret-shaped fields defensively.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from agora_bridge.config import bridge_home

FORBIDDEN_FIELDS = {"private_key", "secret", "token", "password", "api_key", "session_token"}


class LocalAuditLog:
    def __init__(self, path: Path | None = None):
        self.path = path or bridge_home() / "audit.log"

    def record(self, action: str, **fields: object) -> None:
        clean = {k: v for k, v in fields.items() if k.lower() not in FORBIDDEN_FIELDS}
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "action": action,
            **clean,
        }
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
        if self.path.stat().st_mode & 0o077:
            self.path.chmod(0o600)

    def tail(self, n: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().strip().splitlines()[-n:]
        return [json.loads(line) for line in lines]
