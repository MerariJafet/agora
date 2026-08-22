"""Boundary schema validation: unknown/invalid security-critical fields are
rejected, never silently accepted."""

import pytest
from agora_api.boundary import (
    validate_challenge_request,
    validate_event_envelope,
    validate_register_request,
)
from agora_api.errors import ValidationFailed

VALID_KEY = "A" * 43
VALID_SIG = "B" * 86


def test_challenge_request_valid():
    validate_challenge_request({"public_key": VALID_KEY, "agent_name": "Genesis"})


def test_unknown_field_rejected():
    with pytest.raises(ValidationFailed):
        validate_challenge_request(
            {"public_key": VALID_KEY, "agent_name": "G", "admin": True}
        )


def test_private_key_field_structurally_impossible():
    """SEC-001 support: the wire contract has no slot for key material."""
    with pytest.raises(ValidationFailed):
        validate_register_request(
            {
                "challenge_id": "chl_" + "0" * 26,
                "public_key": VALID_KEY,
                "agent_name": "G",
                "signature": VALID_SIG,
                "idempotency_key": "k" * 16,
                "private_key": "should-never-be-accepted",
            }
        )


def test_bad_id_namespace_rejected():
    with pytest.raises(ValidationFailed):
        validate_register_request(
            {
                "challenge_id": "evt_" + "0" * 26,  # wrong namespace
                "public_key": VALID_KEY,
                "agent_name": "G",
                "signature": VALID_SIG,
                "idempotency_key": "k" * 16,
            }
        )


def test_event_envelope_rejects_unknown_fields():
    envelope = {
        "event_id": "evt_" + "0" * 26,
        "event_type": "agent.registered",
        "occurred_at": "2026-08-22T00:00:00Z",
        "actor": {"agent_id": "agt_" + "0" * 26},
        "payload": {},
        "schema_version": "1.0",
    }
    validate_event_envelope(envelope)
    with pytest.raises(ValidationFailed):
        validate_event_envelope(envelope | {"grant_local_permission": "shell.execute"})
