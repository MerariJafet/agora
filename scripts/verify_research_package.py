#!/usr/bin/env python3
"""Offline verification of exported preimages. Requires a trusted candidate hash."""

import argparse
import json
import sys
from pathlib import Path

# Source checkout only; this module and this script use the Python standard library.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from agora_api.research_export import verify_package  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--expected-candidate-hash", required=True)
    args = parser.parse_args()
    try:
        result = verify_package(json.loads(args.package.read_text()), args.expected_candidate_hash)
    except (ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Verification failed: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
