#!/usr/bin/env python3
"""Offline replay with a trusted application genesis hash; not a BFT light client."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "native"))
from tokoin_native.core import digest, require
from tokoin_native.store import Store


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("export", type=Path)
    p.add_argument("--expected-genesis-hash", required=True)
    args = p.parse_args()
    export = json.loads(args.export.read_text())
    require(
        digest("tokoin.genesis.v2", export["genesis"]) == args.expected_genesis_hash,
        "untrusted genesis",
    )
    with tempfile.TemporaryDirectory(prefix="tokoin-replay-") as tmp:
        store = Store(Path(tmp) / "verify.sqlite", export["genesis"])
        for block in export["blocks"]:
            store.prepare(block["transactions"], block["height"], block["timestamp"])
            require(store.pending[1] == block, "block mismatch")
            store.commit()
        print(
            json.dumps(
                {
                    "height": store.state["height"],
                    "state_root": digest("tokoin.state.v2", store.state),
                    "manifest_hash": store.manifest()["manifest_hash"],
                    "consensus_signatures_verified": False,
                    "genesis_recognition_eligible": False,
                },
                sort_keys=True,
            )
        )
        store.close()


if __name__ == "__main__":
    main()
