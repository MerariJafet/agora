"""Mandatory Sprint 10 E2E: Public Alpha gate.

This is intentionally a local-operational drill, not a deploy. It proves the
final roadmap gate can report threats, moderate, run safe chaos simulations,
separate AGORA costs from owner inference, and confirm that there is no
Sprint 11 scope.
"""

import pytest
from agora_api.config import get_settings

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.e2e


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def test_public_alpha_gate(api_client, unique_name, monkeypatch):
    admin = await register_agent(api_client, SigningKeypair(), f"{unique_name}-AlphaAdmin")
    monkeypatch.setattr(get_settings(), "alpha_admin_agent_ids", [admin["agent_id"]])

    dashboard = (await api_client.get("/v1/alpha/dashboard")).json()
    assert "no_sprint_11" in dashboard["readiness"]["checks"]
    assert dashboard["readiness"]["checks"]["public_deploy_not_performed"] is True

    report = await api_client.post(
        "/v1/moderation/reports",
        json={
            "target_type": "artifact",
            "target_id": "arv_00000000000000000000000000",
            "reason": "Alpha red-team fixture requires quarantine and review.",
            "severity": "critical",
            "evidence_refs": ["fixture://prompt-injection", "fixture://archive-bomb"],
        },
        headers=_auth(admin),
    )
    assert report.status_code == 201, report.text
    blocked = (await api_client.get("/v1/alpha/readiness")).json()
    assert blocked["status"] == "NO_GO"

    for action in ("quarantine", "review", "appeal", "resolve"):
        acted = await api_client.post(
            f"/v1/moderation/reports/{report.json()['report_id']}/actions",
            json={"action": action, "reason": f"Alpha gate {action} step."},
            headers=_auth(admin),
        )
        assert acted.status_code == 201, acted.text
        assert acted.json()["action"]["reputation_effect"] == "none"

    drills = []
    for drill_type in ("backup_restore", "outbox_redelivery", "realtime_10k_synthetic"):
        response = await api_client.post(
            "/v1/alpha/drills",
            json={"drill_type": drill_type, "scope": "public-alpha-e2e"},
            headers=_auth(admin),
        )
        assert response.status_code == 201, response.text
        drills.append(response.json())
    assert drills[-1]["result"]["target_connections"] == 10000
    assert drills[-1]["result"]["llm_calls"] == 0

    feedback = await api_client.post(
        "/v1/alpha/feedback",
        json={"category": "security", "message": "Alpha report path works locally."},
        headers=_auth(admin),
    )
    assert feedback.status_code == 201

    costs = (await api_client.get("/v1/alpha/costs")).json()
    assert costs["owner_inference_cost"] == "external_to_agora"
    assert costs["real_charges_enabled"] is False

    final = (await api_client.get("/v1/alpha/dashboard")).json()
    assert final["readiness"]["checks"]["no_sprint_11"] is True
    assert final["readiness"]["checks"]["no_known_secret_requirement"] is True
    assert final["readiness"]["checks"]["public_deploy_not_performed"] is True
    assert {"identity_recovery", "device_key_rotation", "backup_restore"} <= set(
        final["runbooks"]
    )
