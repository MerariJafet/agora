"""BudgetManager contracts (S1-T08). No model calls happen in Sprint 01, but
the enforcement surface exists so later sprints plug consumption in without
changing callers."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BudgetLimits:
    daily_tokens: int = 0        # 0 = nothing allowed until the owner raises it
    daily_usd: float = 0.0
    max_concurrency: int = 1
    schedule: dict | None = None  # {"start": "HH:MM", "end": "HH:MM"} local time


@dataclass
class BudgetUsage:
    tokens_today: int = 0
    usd_today: float = 0.0
    active_tasks: int = 0


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    reason: str


class BudgetManager:
    def __init__(self, limits: BudgetLimits, usage: BudgetUsage | None = None):
        self.limits = limits
        self.usage = usage or BudgetUsage()

    def can_spend(self, tokens: int = 0, usd: float = 0.0, now: datetime | None = None) -> BudgetDecision:
        if self.usage.active_tasks >= self.limits.max_concurrency:
            return BudgetDecision(False, "concurrency limit reached")
        if self.usage.tokens_today + tokens > self.limits.daily_tokens:
            return BudgetDecision(False, "daily token budget exceeded")
        if self.usage.usd_today + usd > self.limits.daily_usd:
            return BudgetDecision(False, "daily monetary budget exceeded")
        if self.limits.schedule and now is not None:
            hhmm = now.strftime("%H:%M")
            start, end = self.limits.schedule["start"], self.limits.schedule["end"]
            inside = start <= hhmm <= end if start <= end else (hhmm >= start or hhmm <= end)
            if not inside:
                return BudgetDecision(False, "outside operating schedule")
        return BudgetDecision(True, "within budget")

    def record(self, tokens: int = 0, usd: float = 0.0) -> None:
        self.usage.tokens_today += tokens
        self.usage.usd_today += usd
