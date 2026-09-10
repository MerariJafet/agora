"""Deterministic sensitivity models, not forecasts or approved monetary policy."""

import json
from pathlib import Path

UNIT = 100_000_000
CAP = 1_000_000 * UNIT


def simulate() -> dict:
    rows = []
    for model in ("fixed_1", "evidence_bands_1_3_10", "annual_budget_10000"):
        for scenario, successes in {
            "low": 12,
            "medium": 365,
            "high": 3650,
            "every_30_minutes": 17520,
        }.items():
            created = 0
            milestones: dict[str, int] = {}
            annual = []
            for year in range(1, 101):
                amounts = []
                for i in range(successes):
                    requested = (
                        UNIT
                        if model == "fixed_1"
                        else (1, 3, 10)[i % 3] * UNIT
                        if model == "evidence_bands_1_3_10"
                        else (10000 * UNIT // successes + (i < 10000 * UNIT % successes))
                    )
                    # Reject whole reward: never silently truncate an authorization.
                    amount = requested if created + requested <= CAP else 0
                    created += amount
                    amounts.append(amount)
                for pct in (25, 50, 90, 100):
                    if created >= CAP * pct // 100:
                        milestones.setdefault(str(pct), year)
                ordered = sorted(amounts)
                median2 = ordered[(len(ordered) - 1) // 2] + ordered[len(ordered) // 2]
                annual.append(
                    {
                        "year": year,
                        "issued_units": sum(amounts),
                        "remaining_units": CAP - created,
                        "median_reward_twice_units": median2,
                    }
                )
            rows.append(
                {
                    "model": model,
                    "scenario": scenario,
                    "successes_per_year": successes,
                    "milestones_year": milestones,
                    "exhaustion_year_within_100_years": milestones.get("100"),
                    "horizons": {str(h): annual[h - 1] for h in (10, 25, 50, 100)},
                    "annual": annual,
                }
            )
    return {
        "status": "SENSITIVITY_NOT_FORECAST",
        "year_days": 365,
        "assumptions": [
            "All counted successes meet scientific requirements.",
            "Uniform synthetic evidence-band cycle; not measured quality.",
            "No revocations; one-year maturation shifts spendability.",
            "No pilot/mainnet recognition or financial price inference.",
            "Annual budget model assumes success count known in advance; "
            "requires epochs before production use.",
            "Median is stored doubled to avoid fractional base units.",
        ],
        "rows": rows,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = simulate()
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"models": 3, "scenarios": 4, "years_each": 100, "output": str(args.output)}))
