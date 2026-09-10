"""Computational TEST agent. Input contains a task, never a reference answer.

No network, models, university impersonation or monetary operations. Each caller
runs a fresh process; trial division and sieve have distinct implementations.
"""

from __future__ import annotations

import hashlib
import json
import sys


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def execute(task: dict) -> dict:
    low, high = task.get("low"), task.get("high")
    if low is None or high is None:
        return {"status": "INSUFFICIENT_EVIDENCE", "reason": "Closed interval unspecified"}
    if not (isinstance(low, int) and isinstance(high, int) and 0 <= low <= high <= 100000):
        raise ValueError("Bounded integer experiment required")
    method = task["method"]
    if method in {"trial_division", "faulty_exclusive_upper"}:
        stop = high if method == "faulty_exclusive_upper" else high + 1
        primes = [
            n
            for n in range(max(2, low), stop)
            if all(n % divisor for divisor in range(2, __import__("math").isqrt(n) + 1))
        ]
    elif method == "sieve":
        flags = [True] * (high + 1)
        flags[:2] = [False, False]
        for n in range(2, __import__("math").isqrt(high) + 1):
            if flags[n]:
                for multiple in range(n * n, high + 1, n):
                    flags[multiple] = False
        primes = [n for n in range(low, high + 1) if flags[n]]
    else:
        raise ValueError("Unknown experimental method")
    evidence = {"interval": [low, high], "method": method, "primes": primes, "count": len(primes)}
    return {
        "status": "EXECUTED",
        "evidence": evidence,
        "evidence_sha256": hashlib.sha256(canonical(evidence)).hexdigest(),
    }


if __name__ == "__main__":
    print(canonical(execute(json.load(sys.stdin))).decode())
