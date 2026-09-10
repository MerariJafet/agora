"""Bounded review-only signals. Similarity or shared ownership is never guilt."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from difflib import SequenceMatcher


def review_signals(contributions: list[dict], votes: list[dict]) -> list[dict]:
    if len(contributions) > 200 or len(votes) > 1000:
        raise ValueError("Bounded pilot analysis required")
    signals = []
    normalized = []
    for row in contributions:
        content = row["content"]
        if not isinstance(content, str) or len(content) > 10000:
            raise ValueError("Bounded textual contributions required")
        normalized.append((row, " ".join(re.findall(r"\w+", content.casefold()))))
    for i, (left, a) in enumerate(normalized):
        for right, b in normalized[i + 1 :]:
            if left["agent_id"] == right["agent_id"] or not a or not b:
                continue
            similarity = SequenceMatcher(None, a, b, autojunk=False).ratio()
            if a == b or similarity >= 0.70:
                signals.append(
                    {
                        "kind": "EXACT_COPY" if a == b else "SIMILARITY_REVIEW",
                        "contribution_ids": [left["id"], right["id"]],
                        "sha256": [hashlib.sha256(t.encode()).hexdigest() for t in (a, b)],
                        "similarity_basis_points": int(similarity * 10000),
                        "action": "REVIEW_ONLY_NO_AUTOMATIC_PENALTY",
                    }
                )
    groups = defaultdict(set)
    for vote in votes:
        if vote.get("owner_id"):
            groups[(vote["target_id"], vote["owner_id"], vote["verdict"])].add(vote["agent_id"])
    for (target, owner, verdict), agents in sorted(groups.items()):
        if len(agents) > 1:
            signals.append(
                {
                    "kind": "SHARED_OWNER_VOTE_CLUSTER",
                    "target_id": target,
                    "owner_id": owner,
                    "verdict": verdict,
                    "agents": sorted(agents),
                    "action": "REVIEW_ONLY_NOT_PROOF_OF_COLLUSION",
                }
            )
    return signals
