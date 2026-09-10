#!/usr/bin/env python3
"""Static local-clock guard for native consensus transitions, plus time inventory."""

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PURE = [
    "native/tokoin_native/core.py",
    "native/tokoin_native/protocol_time.py",
    "native/tokoin_native/v03_science.py",
]
FORBIDDEN = {
    "time",
    "datetime",
    "random",
    "secrets",
    "os",
    "socket",
    "subprocess",
    "requests",
    "httpx",
    "urllib",
}


def violations(source):
    tree = ast.parse(source)
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN:
                    errors.append(
                        {
                            "line": node.lineno,
                            "reason": "nondeterministic import",
                            "name": alias.name,
                        }
                    )
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in FORBIDDEN:
            errors.append(
                {"line": node.lineno, "reason": "nondeterministic import", "name": node.module}
            )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id
            in {"eval", "exec", "__import__", "open", "getattr", "globals", "locals"}
        ):
            errors.append(
                {"line": node.lineno, "reason": "dynamic access forbidden", "name": node.func.id}
            )
    return errors


def inspect():
    failures = [
        {"path": path, **error} for path in PURE for error in violations((ROOT / path).read_text())
    ]
    inventory = []
    paths = []
    for directory in ["native", "apps/api/agora_api", "bridge/agora_bridge", "apps/web"]:
        for p in (ROOT / directory).rglob("*"):
            if p.suffix not in (".py", ".ts", ".tsx") or any(
                x in p.parts for x in ("node_modules", ".next", "vendor", "__pycache__")
            ):
                continue
            paths.append(p)
    tokens = (
        "datetime.now(",
        "datetime.utcnow(",
        "time.time(",
        "time.monotonic(",
        "time.perf_counter(",
        "Date.now(",
        "new Date(",
        "now_utc(",
        ".time.seconds",
        '["time"]',
        "['time']",
        "ProtocolTime(",
    )
    for p in sorted(paths):
        rel = str(p.relative_to(ROOT))
        category = (
            "consensus_critical"
            if rel in PURE or rel == "native/tokoin_native/abci_server.py"
            else "UI_only"
            if rel.startswith("apps/web/")
            else "protocol_noncritical"
        )
        for number, line in enumerate(p.read_text().splitlines(), 1):
            if any(token in line for token in tokens):
                inventory.append(
                    {
                        "path": rel,
                        "line": number,
                        "category": category,
                        "expression": line.strip()[:250],
                    }
                )
    return {
        "status": "PASS" if not failures else "FAIL",
        "critical_scope": PURE,
        "files_scanned": len(paths),
        "failures": failures,
        "time_uses": inventory,
        "coverage_statement": (
            "All matched time expressions in first-party source inventoried; "
            "dynamic/third-party uses are not proven absent. "
            "Pure transitions prohibit imports/dynamic access."
        ),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = inspect()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "time_uses"}))
    raise SystemExit(bool(result["failures"]))
