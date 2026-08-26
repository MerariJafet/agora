"""Bridge-side signed world-rule feed consumer.

This is technical runtime plumbing, not Agent cognition. It never calls a
provider model and never writes memory/personality files. It receives signed
world rules, verifies them locally against AGORA's trust bootstrap, advances a
durable cursor, and sends the Agent's authenticated compatibility attestation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from agora_bridge.client import ApiError, ConnectionClient
from agora_bridge.config import bridge_home

RULE_FEED_PROTOCOL_VERSION = "world-rules-feed.v1"
RULE_SIGNATURE_DOMAIN = "agora.world.rules.v1"
DEFAULT_WORLD_INSTANCE_ID = "agora-local-real"
CURSOR_FILE = "rule-feed-cursor.json"


class RuleFeedError(RuntimeError):
    """Rule feed processing failed without changing acceptance cursor."""


@dataclass(frozen=True)
class RuleProcessingResult:
    rule_id: str
    sequence_number: int
    technical_state: str
    canonical_hash: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def canonical_json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _signed_payload_bytes(payload: dict[str, Any], domain: str) -> bytes:
    return json.dumps(
        {"domain": domain, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _cursor_path() -> Path:
    return bridge_home() / CURSOR_FILE


def _load_cursor() -> dict[str, Any]:
    path = _cursor_path()
    if not path.exists():
        return {
            "schema_version": "1.0",
            "accepted_sequence": 0,
            "processed": {},
            "failures": {},
        }
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleFeedError("RULE_CURSOR_CORRUPT") from exc
    if not isinstance(data, dict):
        raise RuleFeedError("RULE_CURSOR_CORRUPT")
    data.setdefault("schema_version", "1.0")
    data.setdefault("accepted_sequence", 0)
    data.setdefault("processed", {})
    data.setdefault("failures", {})
    return data


def _write_cursor(cursor: dict[str, Any]) -> None:
    path = _cursor_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{CURSOR_FILE}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(cursor, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _trusted_keys(trust_bootstrap: dict[str, Any]) -> dict[str, str]:
    return {
        str(key["key_id"]): str(key["public_key"])
        for key in trust_bootstrap.get("active_keys", [])
        if key.get("status") == "active" and key.get("algorithm") == "Ed25519"
    }


def _required_payload(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": rule["rule_id"],
        "sequence_number": rule["sequence_number"],
        "world_instance_id": rule["world_instance_id"],
        "canonical_hash": rule["canonical_hash"],
        "constitution_hash": rule["constitution_hash"],
    }


def verify_signed_rule(
    rule: dict[str, Any],
    trust_bootstrap: dict[str, Any],
    *,
    expected_world_instance_id: str = DEFAULT_WORLD_INSTANCE_ID,
) -> None:
    required = {
        "rule_id",
        "version",
        "sequence_number",
        "world_instance_id",
        "scope",
        "canonical_body",
        "canonical_hash",
        "constitution_hash",
        "signature",
        "minimum_protocol_version",
    }
    missing = sorted(required - set(rule))
    if missing:
        raise RuleFeedError(f"RULE_FIELD_MISSING:{','.join(missing)}")
    if rule["world_instance_id"] != expected_world_instance_id:
        raise RuleFeedError("WORLD_INSTANCE_MISMATCH")
    if rule["minimum_protocol_version"] != RULE_FEED_PROTOCOL_VERSION:
        raise RuleFeedError("PROTOCOL_INCOMPATIBLE")
    if rule["constitution_hash"] != trust_bootstrap.get("constitution_hash"):
        raise RuleFeedError("CONSTITUTION_HASH_MISMATCH")
    if canonical_json_hash(rule["canonical_body"]) != rule["canonical_hash"]:
        raise RuleFeedError("CANONICAL_HASH_MISMATCH")
    envelope = rule["signature"]
    if not isinstance(envelope, dict):
        raise RuleFeedError("RULE_SIGNATURE_MISSING")
    if envelope.get("domain") != RULE_SIGNATURE_DOMAIN:
        raise RuleFeedError("RULE_SIGNATURE_DOMAIN_MISMATCH")
    if envelope.get("algorithm") != "Ed25519":
        raise RuleFeedError("RULE_SIGNATURE_ALGORITHM_UNSUPPORTED")
    key_id = str(envelope.get("key_id"))
    public_key = _trusted_keys(trust_bootstrap).get(key_id)
    if not public_key:
        raise RuleFeedError("WORLD_KEY_UNKNOWN")
    payload = _required_payload(rule)
    raw = _signed_payload_bytes(payload, RULE_SIGNATURE_DOMAIN)
    if envelope.get("payload_hash") != hashlib.sha256(raw).hexdigest():
        raise RuleFeedError("RULE_SIGNATURE_PAYLOAD_HASH_MISMATCH")
    try:
        Ed25519PublicKey.from_public_bytes(_b64url_decode(public_key)).verify(
            _b64url_decode(str(envelope.get("signature"))), raw
        )
    except Exception as exc:  # noqa: BLE001
        raise RuleFeedError("RULE_SIGNATURE_INVALID") from exc


def _already_processed(cursor: dict[str, Any], rule: dict[str, Any]) -> bool:
    processed = cursor.get("processed", {})
    key = str(rule["rule_id"])
    item = processed.get(key)
    return (
        isinstance(item, dict)
        and item.get("sequence_number") == rule["sequence_number"]
        and item.get("canonical_hash") == rule["canonical_hash"]
        and item.get("technical_state") == "compatible"
    )


def _record_failure(cursor: dict[str, Any], rule: dict[str, Any] | None, reason: str) -> None:
    key = str(rule.get("rule_id") if isinstance(rule, dict) else "feed")
    cursor.setdefault("failures", {})[key] = {
        "reason": reason,
        "at": _now_iso(),
        "next_retry_at": time.time() + 5.0 + (secrets.randbelow(10_000) / 1000.0),
    }
    _write_cursor(cursor)


def process_signed_rule_feed(client: ConnectionClient, token: str) -> list[RuleProcessingResult]:
    """Fetch, verify, cursor and attest all pending signed world rules.

    Re-running this function is safe: already-compatible rules are skipped from
    local reprocessing, and the server attestation endpoint is idempotent.
    """

    cursor = _load_cursor()
    after_sequence = int(cursor.get("accepted_sequence") or 0)
    trust_bootstrap = client.world_trust_bootstrap()
    try:
        feed = client.world_rule_feed(token, after_sequence=after_sequence)
    except ApiError as exc:
        _record_failure(cursor, None, f"RULE_FEED_UNAVAILABLE:{exc.code}")
        raise
    if feed.get("protocol_version") not in {None, RULE_FEED_PROTOCOL_VERSION}:
        _record_failure(cursor, None, "PROTOCOL_INCOMPATIBLE")
        raise RuleFeedError("PROTOCOL_INCOMPATIBLE")
    results: list[RuleProcessingResult] = []
    for rule in feed.get("rules", []):
        if _already_processed(cursor, rule):
            continue
        try:
            verify_signed_rule(rule, trust_bootstrap)
        except RuleFeedError as exc:
            _record_failure(cursor, rule if isinstance(rule, dict) else None, str(exc))
            raise
        client.mark_world_rule_cursor(token, rule["rule_id"], int(rule["sequence_number"]))
        attestation = {
            "rule_id": rule["rule_id"],
            "canonical_hash": rule["canonical_hash"],
            "decision": "compatible",
            "technical_cause": "RULE_ATTESTED",
            "runtime_version": os.environ.get("AGORA_RUNTIME_VERSION", "unknown"),
            "runtime_protocol_version": RULE_FEED_PROTOCOL_VERSION,
            "verification_result": "signature_and_hash_verified",
            "attested_at": _now_iso(),
            "world_instance_id": rule["world_instance_id"],
            "sequence_number": int(rule["sequence_number"]),
        }
        accepted = client.attest_world_rule_versioned(token, attestation)
        cursor["accepted_sequence"] = max(after_sequence, int(rule["sequence_number"]))
        cursor.setdefault("processed", {})[str(rule["rule_id"])] = {
            "sequence_number": int(rule["sequence_number"]),
            "canonical_hash": rule["canonical_hash"],
            "technical_state": accepted["technical_state"],
            "processed_at": _now_iso(),
        }
        cursor.setdefault("failures", {}).pop(str(rule["rule_id"]), None)
        _write_cursor(cursor)
        after_sequence = int(cursor["accepted_sequence"])
        results.append(
            RuleProcessingResult(
                rule_id=str(rule["rule_id"]),
                sequence_number=int(rule["sequence_number"]),
                technical_state=str(accepted["technical_state"]),
                canonical_hash=str(rule["canonical_hash"]),
            )
        )
    return results
