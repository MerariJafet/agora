"""A2A local inbox (S2-T17): bounded, deduplicating, trust-preserving.

Tasks arrive from the AGORA relay as untrusted remote content. The inbox
grants NOTHING: a task exposes work to a RuntimeAdapter, which may accept,
reject or respond — never mutate Bridge configuration or policy.
"""

from collections import OrderedDict
from typing import Any

from agora_bridge.trust import wrap_untrusted

INBOX_LIMIT = 100
SEEN_LIMIT = 1000


class A2AInbox:
    def __init__(self, limit: int = INBOX_LIMIT):
        self.limit = limit
        self._pending: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._seen: OrderedDict[str, None] = OrderedDict()
        self.duplicates_dropped = 0
        self.overflow_dropped = 0

    def offer(self, task_frame: dict[str, Any]) -> bool:
        """Accept a relayed task. Duplicate task_ids are dropped (duplicate
        relay delivery must not run a task twice — SEC-009). Overflow beyond
        the bound is dropped, never buffered unboundedly."""
        task_id = task_frame.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            return False
        if task_id in self._seen:
            self.duplicates_dropped += 1
            return False
        if len(self._pending) >= self.limit:
            self.overflow_dropped += 1
            return False
        self._seen[task_id] = None
        while len(self._seen) > SEEN_LIMIT:
            self._seen.popitem(last=False)
        self._pending[task_id] = wrap_untrusted(task_frame, source="agora-a2a-relay")
        return True

    def take(self) -> dict[str, Any] | None:
        """Pop the oldest pending task (wrapped as untrusted content)."""
        if not self._pending:
            return None
        _, wrapped = self._pending.popitem(last=False)
        return wrapped

    def pending_count(self) -> int:
        return len(self._pending)
