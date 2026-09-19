"""Whether a runtime can still enter a world whose rules have moved.

A runtime used to demand that the world publish *exactly* the rules version it
was written against. That turned every lawful world update into a fleet-wide
outage: the world bumps 1.5.0 -> 1.6.0, every Agent dies at the handshake, and
the symptom on the operator's side looks like apathy rather than a version
mismatch (the same failure shape as ADR-0073's capability-intention gap).

The world's rules version is semantic:

- **PATCH / MINOR** bumps add or clarify law. A runtime that predates them is
  still a lawful inhabitant — it simply does not yet know about a new rule, so
  it enters and the caller is told what it is missing.
- **MAJOR** bumps change the protocol itself. Entering would mean acting under
  law the runtime cannot honor, so this stays fatal.
- A world **older** than the runtime's minimum is also fatal: the runtime would
  be relying on guarantees (vote expiry, review windows, a review floor) that
  this world has not enacted.
"""

from __future__ import annotations

from dataclasses import dataclass

CURRENT = "current"
WORLD_AHEAD = "world_ahead"
WORLD_BEHIND = "world_behind"
MAJOR_MISMATCH = "major_mismatch"
UNPARSEABLE = "unparseable"


@dataclass(frozen=True)
class RulesVerdict:
    status: str
    message: str

    @property
    def can_enter(self) -> bool:
        return self.status in {CURRENT, WORLD_AHEAD}

    @property
    def should_warn(self) -> bool:
        return self.status == WORLD_AHEAD


def parse_version(raw: str) -> tuple[int, int, int] | None:
    parts = str(raw).strip().split(".")
    if len(parts) != 3:
        return None
    try:
        major, minor, patch = (int(part) for part in parts)
    except ValueError:
        return None
    if major < 0 or minor < 0 or patch < 0:
        return None
    return major, minor, patch


def evaluate_rules_version(published: str, *, minimum: str) -> RulesVerdict:
    """Compare the world's published rules version against this runtime's floor."""
    world = parse_version(published)
    floor = parse_version(minimum)
    if floor is None:
        return RulesVerdict(
            UNPARSEABLE, f"runtime minimum rules version is not semantic: {minimum!r}"
        )
    if world is None:
        return RulesVerdict(
            UNPARSEABLE, f"world published a non-semantic rules_version: {published!r}"
        )
    if world[0] != floor[0]:
        return RulesVerdict(
            MAJOR_MISMATCH,
            f"world rules {published} crosses a major boundary from this runtime's "
            f"minimum {minimum}; the protocol itself changed, so entering would mean "
            "acting under law this runtime cannot honor",
        )
    if world < floor:
        return RulesVerdict(
            WORLD_BEHIND,
            f"world rules {published} are older than this runtime's minimum {minimum}; "
            "this runtime relies on guarantees the world has not enacted yet",
        )
    if world > floor:
        return RulesVerdict(
            WORLD_AHEAD,
            f"world rules {published} are newer than this runtime's minimum {minimum}; "
            "entering anyway — read the entry briefing and the plaza update announcements "
            "for the law added since",
        )
    return RulesVerdict(CURRENT, f"world rules {published} match this runtime's minimum")
