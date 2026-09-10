"""Consensus-derived integer seconds. No system clock, timezone or scheduling I/O."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProtocolTime:
    seconds: int

    def __post_init__(self):
        if type(self.seconds) is not int or not 0 <= self.seconds <= 100_000_000_000_000:
            raise ValueError("invalid protocol time")

    @classmethod
    def from_consensus(cls, seconds: int, previous: int) -> "ProtocolTime":
        now = cls(seconds)
        if now.seconds < cls(previous).seconds:
            raise ValueError("non-monotonic time")
        return now

    def deadline(self, duration: int) -> int:
        if type(duration) is not int or duration < 0:
            raise ValueError("invalid duration")
        return ProtocolTime(self.seconds + duration).seconds

    def reached(self, deadline: int) -> bool:
        return self.seconds >= ProtocolTime(deadline).seconds
