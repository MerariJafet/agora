#!/usr/bin/env python3
"""Standalone TOKOIN chain verifier.

Usage:
  scripts/verify-tokoin-chain.py http://127.0.0.1:8700/v1/tokoins/blockchain/export
  scripts/verify-tokoin-chain.py /path/to/tokoin-export.json
  curl -fsS .../export | scripts/verify-tokoin-chain.py -

This verifier checks deterministic hashes, block links, Merkle roots and fixed
supply conservation. It does not claim decentralized public consensus.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from urllib.request import urlopen

MAX_SUPPLY_ACEROS = 1_000_000 * 100_000_000


def canonical_json_hash(payload: dict[str, Any], *, domain: str) -> str:
    envelope = {"domain": domain, "payload": payload}
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def ledger_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence": entry["sequence"],
        "entry_type": entry["entry_type"],
        "from_wallet_id": entry.get("from_wallet_id"),
        "to_wallet_id": entry.get("to_wallet_id"),
        "amount": entry["amount"],
        "currency_code": entry["currency_code"],
        "reason": entry["reason"],
        "mission_id": entry.get("mission_id"),
        "event_id": entry.get("event_id"),
        "previous_hash": entry.get("previous_hash"),
        "created_at": entry["created_at"],
    }


def ledger_hash(entry: dict[str, Any]) -> str:
    raw = json.dumps(ledger_payload(entry), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        raise ValueError("empty block")
    level = leaves[:]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            hashlib.sha256((level[index] + level[index + 1]).encode()).hexdigest()
            for index in range(0, len(level), 2)
        ]
    return level[0]


def block_payload(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "height": block["height"],
        "first_sequence": block["first_sequence"],
        "last_sequence": block["last_sequence"],
        "entry_count": block["entry_count"],
        "transaction_merkle_root": block["transaction_merkle_root"],
        "previous_block_hash": block.get("previous_block_hash"),
        "proof_bundle_hash": block["proof_bundle_hash"],
        "created_at": block["created_at"],
    }


def block_hash(block: dict[str, Any]) -> str:
    return canonical_json_hash(block_payload(block), domain="tokoin.block.v1")


def verify(export: dict[str, Any]) -> dict[str, Any]:
    entries = sorted(export.get("ledger_entries", []), key=lambda row: row["sequence"])
    blocks = sorted(export.get("blocks", []), key=lambda row: row["height"])
    wallets = export.get("wallets", [])
    previous_entry_hash = None
    for expected_sequence, entry in enumerate(entries, start=1):
        if entry["sequence"] != expected_sequence:
            return {"valid": False, "reason": "entry_sequence_gap", "sequence": entry["sequence"]}
        if entry.get("previous_hash") != previous_entry_hash:
            return {"valid": False, "reason": "entry_previous_hash_mismatch",
                    "entry_id": entry.get("entry_id")}
        expected_hash = ledger_hash(entry)
        if entry.get("entry_hash") != expected_hash:
            return {"valid": False, "reason": "entry_hash_mismatch",
                    "entry_id": entry.get("entry_id")}
        previous_entry_hash = expected_hash

    by_sequence = {entry["sequence"]: entry for entry in entries}
    previous_block_hash = None
    sealed_entries = 0
    for expected_height, block in enumerate(blocks, start=1):
        if block["height"] != expected_height:
            return {"valid": False, "reason": "block_height_gap", "block_id": block["block_id"]}
        if block.get("previous_block_hash") != previous_block_hash:
            return {"valid": False, "reason": "previous_block_hash_mismatch",
                    "block_id": block["block_id"]}
        block_entries = [
            by_sequence[sequence]
            for sequence in range(block["first_sequence"], block["last_sequence"] + 1)
            if sequence in by_sequence
        ]
        if len(block_entries) != block["entry_count"]:
            return {"valid": False, "reason": "block_entry_count_mismatch",
                    "block_id": block["block_id"]}
        if merkle_root([entry["entry_hash"] for entry in block_entries]) != block[
            "transaction_merkle_root"
        ]:
            return {"valid": False, "reason": "merkle_root_mismatch",
                    "block_id": block["block_id"]}
        proof_hash = canonical_json_hash(
            block["proof_bundle"], domain="tokoin.block_proof_bundle.v1"
        )
        if proof_hash != block["proof_bundle_hash"]:
            return {"valid": False, "reason": "proof_bundle_hash_mismatch",
                    "block_id": block["block_id"]}
        if block_hash(block) != block["block_hash"]:
            return {"valid": False, "reason": "block_hash_mismatch",
                    "block_id": block["block_id"]}
        previous_block_hash = block["block_hash"]
        sealed_entries = block["last_sequence"]

    total_balance = sum(int(wallet["balance_aceros"]) for wallet in wallets)
    if total_balance != MAX_SUPPLY_ACEROS:
        return {"valid": False, "reason": "wallet_supply_mismatch",
                "total_balance_aceros": total_balance}
    return {
        "valid": True,
        "blocks": len(blocks),
        "entries_checked": len(entries),
        "sealed_entries": sealed_entries,
        "tip_hash": previous_block_hash,
        "total_balance_aceros": total_balance,
        "security_model": "tamper_evident_internal_testnet_not_public_consensus",
    }


def load_source(source: str) -> dict[str, Any]:
    if source == "-":
        return json.load(sys.stdin)
    if source.startswith(("http://", "https://")):
        with urlopen(source, timeout=10) as response:  # noqa: S310 - operator-supplied URL.
            return json.load(response)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    result = verify(load_source(argv[1]))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
