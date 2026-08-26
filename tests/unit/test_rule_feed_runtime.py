import base64
import hashlib
import json

import pytest
from agora_bridge.client import ApiError
from agora_bridge.rule_feed import (
    CURSOR_FILE,
    RULE_FEED_PROTOCOL_VERSION,
    RULE_SIGNATURE_DOMAIN,
    RuleFeedError,
    canonical_json_hash,
    process_signed_rule_feed,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _signed_rule(*, bad_signature: bool = False) -> tuple[dict, dict]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    body = {
        "schema_version": "1.0",
        "rules": ["Local private keys remain local."],
        "entry_test": {"private_keys_stay_local": True},
    }
    canonical_hash = canonical_json_hash(body)
    payload = {
        "rule_id": "rule_world_entry_canary_v1",
        "sequence_number": 1,
        "world_instance_id": "agora-local-real",
        "canonical_hash": canonical_hash,
        "constitution_hash": "constitution-test",
    }
    raw = json.dumps(
        {"domain": RULE_SIGNATURE_DOMAIN, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    signature = bytearray(private_key.sign(raw))
    if bad_signature:
        signature[0] ^= 1
    rule = {
        **payload,
        "rule_class": "entry_rules",
        "version": "1.1.0",
        "scope": "world_entry",
        "title": "AGORA World Entry Rules",
        "canonical_body": body,
        "signature": {
            "schema_version": "1.0",
            "domain": RULE_SIGNATURE_DOMAIN,
            "algorithm": "Ed25519",
            "key_id": "world-key",
            "public_key": _b64url(public_key),
            "signature": _b64url(bytes(signature)),
            "payload_hash": hashlib.sha256(raw).hexdigest(),
        },
        "minimum_protocol_version": RULE_FEED_PROTOCOL_VERSION,
        "required_attestation_type": "signature_and_compatibility",
    }
    trust = {
        "constitution_hash": "constitution-test",
        "active_keys": [
            {
                "key_id": "world-key",
                "algorithm": "Ed25519",
                "public_key": _b64url(public_key),
                "status": "active",
            }
        ],
    }
    return rule, trust


class FakeRuleClient:
    def __init__(self, rule: dict, trust: dict):
        self.rule = rule
        self.trust = trust
        self.feed_calls: list[int] = []
        self.cursor_calls: list[tuple[str, int]] = []
        self.attestations: list[dict] = []

    def world_trust_bootstrap(self) -> dict:
        return self.trust

    def world_rule_feed(self, _token: str, after_sequence: int = 0) -> dict:
        self.feed_calls.append(after_sequence)
        rules = [] if self.rule["sequence_number"] <= after_sequence else [self.rule]
        return {"protocol_version": RULE_FEED_PROTOCOL_VERSION, "rules": rules}

    def mark_world_rule_cursor(self, _token: str, rule_id: str, sequence_number: int) -> dict:
        self.cursor_calls.append((rule_id, sequence_number))
        return {"technical_state": "seen"}

    def attest_world_rule_versioned(self, _token: str, body: dict) -> dict:
        self.attestations.append(body)
        return {"technical_state": body["decision"]}


class FeedUnavailableClient(FakeRuleClient):
    def world_rule_feed(self, _token: str, after_sequence: int = 0) -> dict:
        self.feed_calls.append(after_sequence)
        raise ApiError(503, "feed_unavailable", "feed unavailable")


def test_signed_rule_feed_verifies_cursors_and_attests(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    monkeypatch.setenv("AGORA_RUNTIME_VERSION", "unit-runtime")
    rule, trust = _signed_rule()
    client = FakeRuleClient(rule, trust)

    results = process_signed_rule_feed(client, "session-token")

    assert [(r.rule_id, r.technical_state) for r in results] == [
        ("rule_world_entry_canary_v1", "compatible")
    ]
    assert client.cursor_calls == [("rule_world_entry_canary_v1", 1)]
    assert client.attestations[0]["runtime_version"] == "unit-runtime"
    assert client.attestations[0]["runtime_protocol_version"] == RULE_FEED_PROTOCOL_VERSION
    cursor = json.loads((tmp_path / CURSOR_FILE).read_text())
    assert cursor["accepted_sequence"] == 1
    assert cursor["processed"]["rule_world_entry_canary_v1"]["technical_state"] == "compatible"


def test_signed_rule_feed_replay_does_not_double_attest(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    rule, trust = _signed_rule()
    client = FakeRuleClient(rule, trust)

    process_signed_rule_feed(client, "session-token")
    process_signed_rule_feed(client, "session-token")

    assert client.feed_calls == [0, 1]
    assert len(client.attestations) == 1
    assert len(client.cursor_calls) == 1


def test_invalid_signature_does_not_advance_cursor_or_attest(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    rule, trust = _signed_rule(bad_signature=True)
    client = FakeRuleClient(rule, trust)

    with pytest.raises(RuleFeedError, match="RULE_SIGNATURE_INVALID"):
        process_signed_rule_feed(client, "session-token")

    assert client.attestations == []
    assert client.cursor_calls == []
    cursor = json.loads((tmp_path / CURSOR_FILE).read_text())
    assert cursor["accepted_sequence"] == 0
    assert cursor["failures"]["rule_world_entry_canary_v1"]["reason"] == "RULE_SIGNATURE_INVALID"


def test_corrupt_cursor_blocks_processing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    (tmp_path / CURSOR_FILE).write_text("{not-json")
    rule, trust = _signed_rule()
    client = FakeRuleClient(rule, trust)

    with pytest.raises(RuleFeedError, match="RULE_CURSOR_CORRUPT"):
        process_signed_rule_feed(client, "session-token")

    assert client.attestations == []


def test_feed_unavailable_records_retry_without_attestation(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    rule, trust = _signed_rule()
    client = FeedUnavailableClient(rule, trust)

    with pytest.raises(ApiError):
        process_signed_rule_feed(client, "session-token")

    assert client.attestations == []
    cursor = json.loads((tmp_path / CURSOR_FILE).read_text())
    assert cursor["accepted_sequence"] == 0
    assert cursor["failures"]["feed"]["reason"] == "RULE_FEED_UNAVAILABLE:feed_unavailable"
    assert cursor["failures"]["feed"]["next_retry_at"]
