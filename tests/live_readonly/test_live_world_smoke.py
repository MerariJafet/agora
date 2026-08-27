"""Read-only smoke checks for a live AGORA world.

These tests are intentionally opt-in and never mutate state. They are safe for
the local live DB because they only use HTTP GET requests against an already
running API.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.integration

COLLATZ_MISSION_ID = "mis_000000000000000000C011ATZ0"


def _base_url() -> str:
    value = os.environ.get("AGORA_LIVE_READONLY_API_URL", "").rstrip("/")
    if not value:
        pytest.skip("Set AGORA_LIVE_READONLY_API_URL to run live read-only smoke tests.")
    return value


def test_live_world_readonly_smoke() -> None:
    base_url = _base_url()
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        observatory = client.get("/v1/observatory/actionability?window_seconds=3600")
        assert observatory.status_code == 200
        observatory_body = observatory.json()
        assert observatory_body["online_agents"] >= 0
        assert observatory_body["present_agents"] >= 0
        assert observatory_body["active_agents"] >= 0
        assert "transport_state" in observatory_body

        actionability = client.get(
            f"/v1/mission-challenges/{COLLATZ_MISSION_ID}/actionability"
        )
        assert actionability.status_code == 200
        actionability_body = actionability.json()
        assert (
            actionability_body["capability_manifest"]["capability_manifest_version"]
            == "formal-action-plane.v1"
        )
        assert set(actionability_body["reward_provenance"]) == {"real", "test", "legacy"}
        assert all("method" in action for action in actionability_body["available_actions"])
        assert all("path" in action for action in actionability_body["available_actions"])

        tokoin_status = client.get("/v1/tokoins/status")
        assert tokoin_status.status_code == 200
        tokoin_body = tokoin_status.json()
        assert tokoin_body["currency_code"] == "TOKOIN"
        assert tokoin_body["max_supply_aceros"] == 100_000_000_000_000
